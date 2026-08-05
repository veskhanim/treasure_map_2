import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode
from dotenv import load_dotenv

# 1. Явно указываем абсолютный путь к файлу .env
# file - это путь к текущему файлу bot.py, os.path.dirname берёт папку 'bot'
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')

# 2. Загружаем переменные из этого конкретного файла
load_dotenv(dotenv_path=env_path)

# 3. Читаем переменные
BOT_TOKEN = os.getenv('BOT_TOKEN')
APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# 4. ПРОВЕРКА: если токен не загрузился, мы сразу об этом узнаем
if not BOT_TOKEN:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: BOT_TOKEN не найден!")
    print(f"Проверь файл: {env_path}")
    print("Убедись, что в нём нет пробелов вокруг знака '='")
    exit(1)  # Останавливаем программу, чтобы не было ошибки InvalidToken

print("✅ Токен успешно загружен!")

import re
import requests
import time
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== НАСТРОЙКИ =====
# BOT_TOKEN = os.getenv('BOT_TOKEN')
# WEBAPP_URL = os.getenv('WEBAPP_URL')
# APPS_SCRIPT_URL = os.getenv('APPS_SCRIPT_URL')
# YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

# ===== API HELPER =====
def apps_script_request(path, method='GET', body=None, params=None):
    """Запрос к Apps Script"""
    if params is None:
        params = {}
    
    url = f"{APPS_SCRIPT_URL}?path={path}"
    if 'id' in params:
        url += f"&id={params['id']}"
    
    try:
        if method == 'GET':
            response = requests.get(url, timeout=10)
        else:
            headers = {'Content-Type': 'text/plain;charset=utf-8'}
            payload = {**(body or {}), '_method': method}
            response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        print(f"📡 Apps Script Response [{method} {path}]: Status={response.status_code}")
        print(f"📄 Response text (first 500 chars): {response.text[:500]}")
        
        # Проверяем, что ответ не пустой
        if not response.text.strip():
            print(f"❌ Пустой ответ от Apps Script для {path}")
            return {'error': 'Пустой ответ от сервера'}
        
        # Проверяем, что ответ начинается с { или [ (JSON)
        if not response.text.strip().startswith(('{', '[')):
            print(f"❌ Apps Script вернул не JSON для {path}: {response.text[:100]}")
            return {'error': 'Сервер вернул не JSON (возможно HTML ошибка)'}
        
        return response.json()
        
    except requests.exceptions.Timeout:
        print(f" Таймаут при запросе к Apps Script: {path}")
        return {'error': 'Таймаут запроса'}
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при запросе к Apps Script: {e}")
        return {'error': f'Ошибка сети: {str(e)}'}
    except Exception as e:
        print(f"❌ Неизвестная ошибка при запросе к Apps Script: {e}")
        return {'error': f'Неизвестная ошибка: {str(e)}'}

# ===== YOUTUBE API =====
def get_channel_videos(channel_url):
    """Получить видео с канала YouTube"""
    if not YOUTUBE_API_KEY:
        return []
    
    try:
        # Получаем upload playlist ID канала
        channel_response = requests.get(
            'https://www.googleapis.com/youtube/v3/channels',
            params={
                'part': 'contentDetails',
                'id': channel_url,
                'key': YOUTUBE_API_KEY
            }
        ).json()
        
        if not channel_response.get('items'):
            return []
        
        upload_playlist_id = channel_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Получаем последние видео
        playlist_response = requests.get(
            'https://www.googleapis.com/youtube/v3/playlistItems',
            params={
                'part': 'snippet',
                'playlistId': upload_playlist_id,
                'maxResults': 10,
                'key': YOUTUBE_API_KEY
            }
        ).json()
        
        videos = []
        for item in playlist_response.get('items', []):
            videos.append({
                'id': item['snippet']['resourceId']['videoId'],
                'title': item['snippet']['title'],
                'published_at': item['snippet']['publishedAt']
            })
        
        return videos
    except Exception as e:
        print(f"Error fetching channel videos: {e}")
        return []

# ===== КОМАНДЫ =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    keyboard = [
        [InlineKeyboardButton(
            "🗺️ Открыть приложение", 
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    
    await update.message.reply_text(
        'Привет! 👋\n\n'
        'Я бот для управления видео ATEEZ.\n'
        'Нажми кнопку ниже, чтобы открыть приложение:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    await update.message.reply_text(
        ' Справка:\n\n'
        ' Отправьте ссылку на YouTube — видео добавится в pending\n'
        '/app — открыть мини-приложение\n'
        '/channels — список каналов\n'
        '/addchannel <name> <url> [original|translation] — добавить канал\n'
        '/track <channel_id> — включить отслеживание\n'
        '/untrack <channel_id> — выключить отслеживание\n'
        '/settype <channel_id> <original|translation> — тип канала\n'
        '/refresh — обновить видео с отслеживаемых каналов\n'
        '/pending — ожидающие видео\n'
        '/categories — список категорий\n'
        '/addcat <name> <short> — добавить категорию\n'
        '/stats — статистика\n'
        '/help — эта справка'
    )

async def app_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /app"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    keyboard = [
        [InlineKeyboardButton(
            "🗺️ Открыть", 
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    
    await update.message.reply_text(
        'Откройте мини-приложение:',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def channels_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /channels"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    channels = apps_script_request('channels', 'GET')
    
    if not channels:
        await update.message.reply_text(' Каналы не найдены')
        return
    
    msg = '📺 Каналы:\n\n'
    
    originals = [c for c in channels if c.get('type') == 'original']
    translations = [c for c in channels if c.get('type') == 'translation']
    
    if originals:
        msg += '🎬 ОРИГИНАЛЬНЫЕ:\n'
        for c in originals:
            track = '✅' if c.get('tracked') else '⏸️'
            msg += f"  {track} {c['name']} ({c['id']})\n"
        msg += '\n'
    
    if translations:
        msg += '🌐 ПЕРЕВОДЫ:\n'
        for c in translations:
            track = '✅' if c.get('tracked') else '⏸️'
            msg += f"  {track} {c['name']} ({c['id']})\n"
    
    await update.message.reply_text(msg)

async def add_channel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addchannel"""
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addchannel <название> <url> [original|translation]\n\n'
            'Пример: /addchannel KQ ENTERTAINMENT UCaO6TYtlC8U5ttzA2hTrZ4Q original'
        )
        return
    
    # Копируем список аргументов, чтобы не ломать оригинал
    args = context.args.copy()
    
    # 1. Определяем тип канала (последний аргумент, если он original или translation)
    channel_type = 'original'
    if args[-1] in ('original', 'translation'):
        channel_type = args.pop()
    
    # 2. Ссылка на канал (теперь последний аргумент)
    url = args.pop()
    
    # 3. Название канала (всё, что осталось, склеиваем пробелами)
    name = ' '.join(args)
    
    if not name or not url:
        await update.message.reply_text('Неверный формат. Проверьте название и ссылку.')
        return
    
    result = apps_script_request('channels', 'POST', {
        'name': name,
        'url': url,
        'type': channel_type,
        'tracked': False
    })
    
    await update.message.reply_text(
        f"✅ Канал добавлен!\n\n"
        f"ID: {result.get('id')}\n"
        f"Название: {name}\n"
        f"Тип: {channel_type}\n\n"
        f"Используйте /track {result.get('id')} для включения отслеживания."
    )

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /track"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if not context.args:
        await update.message.reply_text('Использование: /track <channel_id>')
        return
    
    channel_id = context.args[0]
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['tracked'] = True
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    await update.message.reply_text(f"✅ Отслеживание канала {channel_id} включено")

async def untrack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /untrack"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if not context.args:
        await update.message.reply_text('Использование: /untrack <channel_id>')
        return
    
    channel_id = context.args[0]
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['tracked'] = False
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    await update.message.reply_text(f"⏸️ Отслеживание канала {channel_id} выключено")

async def set_type_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settype"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text('Использование: /settype <channel_id> <original|translation>')
        return
    
    channel_id = context.args[0]
    channel_type = context.args[1]
    
    if channel_type not in ('original', 'translation'):
        await update.message.reply_text('Тип должен быть: original или translation')
        return
    
    channels = apps_script_request('channels', 'GET')
    channel = next((c for c in channels if c['id'] == channel_id), None)
    
    if not channel:
        await update.message.reply_text('❌ Канал не найден')
        return
    
    channel['type'] = channel_type
    apps_script_request('channels', 'PUT', channel, {'id': channel_id})
    
    type_name = 'оригинальный' if channel_type == 'original' else 'переводческий'
    await update.message.reply_text(f"✅ Тип канала {channel_id} изменен на: {type_name}")

async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /refresh - обновление видео с отслеживаемых каналов"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    await update.message.reply_text('🔄 Обновляю каналы...')
    
    # Получаем отслеживаемые каналы
    channels = apps_script_request('channels', 'GET')
    tracked_channels = [c for c in channels if c.get('tracked')]
    
    if not tracked_channels:
        await update.message.reply_text('📺 Нет отслеживаемых каналов')
        return
    
    # Получаем существующие видео
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    
    existing_ids = set([v['id'] for v in videos] + [p['id'] for p in pending])
    
    total_new = 0
    
    for channel in tracked_channels:
        channel_videos = get_channel_videos(channel['url'])
        
        for video in channel_videos:
            if video['id'] not in existing_ids:
                # Добавляем в pending
                apps_script_request('pending-videos', 'POST', {
                    'id': video_id,
                    'title': oembed_data.get('title', 'Без названия'),
                    'channel_id': channel_id,
                    'channel_name': channel_name,
                    'published_at': published_at,  # dd.mm.yyyy
                    'duration': duration,          # hh.mm
                    'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                    'video_url': f'https://youtube.com/watch?v={video_id}'
                })
                
                existing_ids.add(video['id'])
                total_new += 1
    
    if total_new > 0:
        await update.message.reply_text(f"✅ Найдено {total_new} новых видео!")
    else:
        await update.message.reply_text('✨ Новых видео не найдено')

async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /pending"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    pending = apps_script_request('pending-videos', 'GET')
    
    if not pending:
        await update.message.reply_text('✨ Нет ожидающих видео')
        return
    
    msg = f"⏳ Ожидающие видео ({len(pending)}):\n\n"
    
    for i, v in enumerate(pending[:5], 1):
        msg += f"{i}. {v['title']}\n"
        msg += f"   📺 {v.get('channel_name', 'Неизвестно')}\n\n"
    
    if len(pending) > 5:
        msg += f"... и ещё {len(pending) - 5}\n"
    
    await update.message.reply_text(msg)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /categories"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    categories = apps_script_request('categories', 'GET')
    
    if not categories:
        await update.message.reply_text(' Категории не найдены')
        return
    
    msg = '📂 Категории:\n\n' + '\n'.join(
        [f"• {c['name']} ({c['short_name']})" for c in categories]
    )
    
    await update.message.reply_text(msg)

async def add_category_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /addcat"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    if len(context.args) < 2:
        await update.message.reply_text(
            'Использование: /addcat <название> <краткое>\n\n'
            'Пример: /addcat Music Video MV'
        )
        return
    
    name = context.args[0]
    short = context.args[1]
    
    apps_script_request('categories', 'POST', {
        'name': name,
        'short_name': short
    })
    
    await update.message.reply_text(f"✅ Категория добавлена: {name} ({short})")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats"""
    if not check_access(update.effective_user.id):
        await update.message.reply_text(
            "❌ У вас нет доступа к этому боту.\nОбратитесь к администратору."
        )
        return
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    channels = apps_script_request('channels', 'GET')
    
    originals = len([c for c in channels if c.get('type') == 'original'])
    translations = len([c for c in channels if c.get('type') == 'translation'])
    tracked = len([c for c in channels if c.get('tracked')])
    
    msg = (
        f"📊 Статистика:\n\n"
        f" Видео: {len(videos)}\n"
        f"⏳ Pending: {len(pending)}\n"
        f"📺 Каналы: {len(channels)}\n"
        f"  🎬 Оригинальных: {originals}\n"
        f"  🌐 Переводческих: {translations}\n"
        f"  👁️ Отслеживаемых: {tracked}"
    )
    
    await update.message.reply_text(msg)

import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

async def handle_youtube_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ссылок на YouTube (обычные видео, shorts и live)"""
    text = update.message.text
    
    # Разбиваем текст на строки для анализа
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Паттерн для извлечения всех YouTube ссылок
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/live/)([0-9A-Za-z_-]{11})',
        r'^([0-9A-Za-z_-]{11})$',
    ]
    
    video_ids = []
    unrecognized_lines = []  # ← Строки которые не распознаны
    
    for line in lines:
        found = False
        # Проверяем по полным ссылкам
        for pattern in youtube_patterns[:-1]:
            matches = re.findall(pattern, line)
            if matches:
                video_ids.extend(matches)
                found = True
                break
        
        # Если не нашли по ссылкам, проверяем на чистый ID
        if not found and re.match(youtube_patterns[-1], line):
            video_ids.append(line)
            found = True
        
        # Если ничего не найдено - добавляем в нераспознанные
        if not found:
            unrecognized_lines.append(line)
    
    video_ids = list(set(video_ids))
    
    if not video_ids and not unrecognized_lines:
        return  # Пустое сообщение
    
    # Проверяем существующие видео
    videos = apps_script_request('videos', 'GET')
    pending = apps_script_request('pending-videos', 'GET')
    
    existing_video_ids = set()
    if isinstance(videos, list):
        existing_video_ids.update([str(v.get('id', '')) for v in videos])
    if isinstance(pending, list):
        existing_video_ids.update([str(p.get('id', '')) for p in pending])
    
    new_video_ids = [vid for vid in video_ids if vid not in existing_video_ids]
    already_exist_count = len(video_ids) - len(new_video_ids)
    
    # Если нет видео для добавления И нет нераспознанных строк
    if not new_video_ids and not unrecognized_lines:
        await update.message.reply_text(
            f"⚠️ Все {len(video_ids)} видео уже есть в таблице."
        )
        return
    
    # Если есть только нераспознанные строки
    if not new_video_ids and unrecognized_lines:
        msg = f" Не удалось распознать ни одной ссылки!\n\n"
        msg += f"📊 Статистика:\n"
        msg += f"• Всего строк: {len(lines)}\n"
        msg += f"• Распознано: 0\n"
        msg += f"• Нераспознано: {len(unrecognized_lines)}\n"
        
        if unrecognized_lines:
            msg += f"\n❓ Нераспознанные строки:\n"
            for line in unrecognized_lines[:20]:
                msg += f"• {line}\n"
            if len(unrecognized_lines) > 20:
                msg += f"... и ещё {len(unrecognized_lines) - 20}\n"
        
        await update.message.reply_text(msg)
        return
    
    # Отправляем сообщение о начале обработки
    status_msg = await update.message.reply_text(
        f"🔄 Обрабатываю {len(new_video_ids)} видео...\n\n"
        f"0/{len(new_video_ids)} добавлено"
    )
    
    added_count = 0
    failed_count = 0
    failed_details = []
    
    # Получаем список каналов один раз
    channels = apps_script_request('channels', 'GET')
    
    for i, video_id in enumerate(new_video_ids, 1):
        try:
            # 1. Получаем информацию через oEmbed
            oembed_url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
            oembed_response = requests.get(oembed_url, timeout=10)
            
            if oembed_response.status_code != 200:
                failed_count += 1
                failed_details.append({
                    'id': video_id,
                    'reason': 'Нет доступа к видео (удалено, приватное или не существует)',
                    'url': f'https://youtube.com/watch?v={video_id}'
                })
                continue
            
            oembed_data = oembed_response.json()
            channel_id = 'manual'
            channel_name = oembed_data.get('author_name', 'Неизвестно')
            duration = ''
            published_at = ''
            hashtags = []
            
            # 2. YouTube API
            if YOUTUBE_API_KEY:
                try:
                    api_url = f'https://www.googleapis.com/youtube/v3/videos'
                    api_response = requests.get(
                        api_url,
                        params={
                            'part': 'snippet,contentDetails,liveStreamingDetails',
                            'id': video_id,
                            'key': YOUTUBE_API_KEY
                        },
                        timeout=10
                    )
                    api_data = api_response.json()
                    
                    if not api_data.get('items'):
                        failed_count += 1
                        failed_details.append({
                            'id': video_id,
                            'reason': 'Видео не найдено в API',
                            'url': f'https://youtube.com/watch?v={video_id}'
                        })
                        continue
                    
                    video_info = api_data['items'][0]
                    snippet = video_info['snippet']
                    yt_channel_id = snippet.get('channelId', '')
                    
                    # Извлекаем хэштеги
                    if 'description' in snippet:
                        description = snippet.get('description', '')
                        hashtag_pattern = r'#([a-zA-Z0-9_가-힣]+)'
                        found_tags = re.findall(hashtag_pattern, description)
                        hashtags = list(dict.fromkeys([f'#{tag}' for tag in found_tags]))[:15]
                    
                    # Дата
                    published_at_iso = snippet.get('publishedAt', '')
                    if published_at_iso:
                        pub_date = datetime.fromisoformat(published_at_iso.replace('Z', '+00:00'))
                        published_at = pub_date.strftime('%d.%m.%Y')
                    
                    # Длительность
                    duration_iso = video_info['contentDetails']['duration']
                    if duration_iso:
                        hours = re.search(r'(\d+)H', duration_iso)
                        minutes = re.search(r'(\d+)M', duration_iso)
                        seconds = re.search(r'(\d+)S', duration_iso)
                        
                        h = int(hours.group(1)) if hours else 0
                        m = int(minutes.group(1)) if minutes else 0
                        s = int(seconds.group(1)) if seconds else 0
                        duration = f'{h}:{m:02d}:{s:02d}' if h > 0 else f'{m}:{s:02d}'
                    else:
                        duration = 'LIVE'
                    
                    # Поиск канала
                    if isinstance(channels, list):
                        for ch in channels:
                            ch_url = str(ch.get('url', '')).strip()
                            if ch_url == yt_channel_id or f'youtube.com/channel/{yt_channel_id}' in ch_url:
                                channel_id = ch.get('id', 'manual')
                                channel_name = ch.get('name', channel_name)
                                break
                        
                        if channel_id == 'manual':
                            oembed_name_lower = channel_name.lower().strip()
                            for ch in channels:
                                db_name_lower = str(ch.get('name', '')).lower().strip()
                                if db_name_lower == oembed_name_lower or db_name_lower in oembed_name_lower:
                                    channel_id = ch.get('id', 'manual')
                                    channel_name = ch.get('name', channel_name)
                                    break
                                        
                except Exception as e:
                    failed_count += 1
                    failed_details.append({
                        'id': video_id,
                        'reason': f'Ошибка API: {str(e)[:50]}',
                        'url': f'https://youtube.com/watch?v={video_id}'
                    })
                    continue
            else:
                failed_count += 1
                failed_details.append({
                    'id': video_id,
                    'reason': 'Не указан YouTube API ключ',
                    'url': f'https://youtube.com/watch?v={video_id}'
                })
                continue
            
            # 3. Добавляем в pending
            result = apps_script_request('pending-videos', 'POST', {
                'id': video_id,
                'title': oembed_data.get('title', 'Без названия'),
                'channel_id': channel_id,
                'channel_name': channel_name,
                'published_at': published_at,
                'duration': duration,
                'hashtags': ','.join(hashtags),
                'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                'video_url': f'https://youtube.com/watch?v={video_id}'
            })
            
            if isinstance(result, dict) and result.get('success'):
                added_count += 1
            else:
                failed_count += 1
                failed_details.append({
                    'id': video_id,
                    'reason': f'Ошибка Apps Script: {result.get("error", "Неизвестная")}',
                    'url': f'https://youtube.com/watch?v={video_id}'
                })
            
            # Обновляем прогресс
            if i % 3 == 0 or i == len(new_video_ids):
                await status_msg.edit_text(
                    f" Обрабатываю {len(new_video_ids)} видео...\n\n"
                    f"{added_count}/{len(new_video_ids)} добавлено"
                )
            
        except Exception as e:
            failed_count += 1
            failed_details.append({
                'id': video_id,
                'reason': f'Неизвестная ошибка: {str(e)[:50]}',
                'url': f'https://youtube.com/watch?v={video_id}'
            })
            print(f"❌ Ошибка {video_id}: {e}")
    
    # Формируем итоговое сообщение
    result_msg = f"✅ Готово!\n\n"
    result_msg += f"📊 Статистика:\n"
    result_msg += f"• Всего строк: {len(lines)}\n"
    result_msg += f"• Распознано ссылок: {len(video_ids)}\n"
    result_msg += f"• Уже в таблицах: {already_exist_count}\n"
    result_msg += f"• Добавлено: {added_count}\n"
    result_msg += f"• Ошибок обработки: {failed_count}\n"
    result_msg += f"• Нераспознано: {len(unrecognized_lines)}\n"  # ← НОВОЕ
    
    # Показываем нераспознанные строки
    if unrecognized_lines:
        result_msg += f"\n❓ Нераспознанные строки:\n"
        for line in unrecognized_lines[:20]:  # Первые 20
            result_msg += f"• {line}\n"
        if len(unrecognized_lines) > 20:
            result_msg += f"... и ещё {len(unrecognized_lines) - 20}\n"
    
    # Показываем детали ошибок
    if failed_details:
        result_msg += f"\n❌ Неудачи обработки:\n"
        for fail in failed_details[:10]:
            result_msg += f"• {fail['id']}: {fail['reason']}\n"
            result_msg += f"  {fail['url']}\n"
        
        if len(failed_details) > 10:
            result_msg += f"... и ещё {len(failed_details) - 10}\n"
    
    await status_msg.edit_text(result_msg)

# ===== ПРОВЕРКА ДОСТУПА =====
def check_access(telegram_id: int) -> bool:
    """Проверяет, есть ли у пользователя доступ"""
    try:
        url = f"{APPS_SCRIPT_URL}?path=users"
        print(f"🔍 Запрос к Apps Script: {url}")
        
        response = requests.get(url, timeout=10)
        print(f"📡 Статус ответа: {response.status_code}")
        print(f"📄 Текст ответа: {response.text[:300]}") # Покажет первые 300 символов ответа
        
        # Пробуем распарсить JSON
        users = response.json()
        
        if isinstance(users, list):
            for user in users:
                if str(user.get('telegram_id')) == str(telegram_id):
                    access_val = str(user.get('access')).lower()
                    return access_val in ['true', '1', 'yes']
        return False
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Ошибка сети при проверке доступа: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка парсинга JSON при проверке доступа: {e}")
        return False

async def fix_hashtags_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Временная команда: извлекает хэштеги для всех существующих видео"""
    
    # Проверка доступа (только для администратора)
    if not check_access(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "⚠️ ВНИМАНИЕ: Это временная функция!\n\n"
        "Сейчас я пройдусь по всем видео в таблицах Videos и PendingVideos,\n"
        "извлеку хэштеги из описания и обновлю колонку hashtags.\n\n"
        "Это может занять несколько минут. Начать?"
    )
    
    status_msg = await update.message.reply_text("🔄 Начинаю обработку...")
    
    try:
        # Получаем все видео из обеих таблиц
        videos = apps_script_request('videos', 'GET')
        pending = apps_script_request('pending-videos', 'GET')
        
        if not isinstance(videos, list):
            videos = []
        if not isinstance(pending, list):
            pending = []
        
        total = len(videos) + len(pending)
        if total == 0:
            await status_msg.edit_text("Нет видео для обработки")
            return
        
        await status_msg.edit_text(
            f"📊 Найдено видео:\n"
            f"• Videos: {len(videos)}\n"
            f"• Pending: {len(pending)}\n"
            f"• Всего: {total}\n\n"
            f"🔄 Начинаю обработку..."
        )
        
        updated_count = 0
        skipped_count = 0
        failed_count = 0
        failed_ids = []
        
        # Обрабатываем Videos
        for i, video in enumerate(videos, 1):
            video_id = str(video.get('id', ''))
            if not video_id:
                continue
            
            try:
                hashtags = await extract_hashtags_from_youtube(video_id)
                
                if hashtags is not None:
                    result = apps_script_request('update-hashtags', 'PUT', {
                        'sheet_name': 'Videos',
                        'id': video_id,
                        'hashtags': hashtags
                    })
                    
                    if isinstance(result, dict) and result.get('success'):
                        updated_count += 1
                    else:
                        failed_count += 1
                        failed_ids.append(f"V:{video_id}")
                else:
                    skipped_count += 1
                
                # Обновляем прогресс каждые 5 видео
                if i % 5 == 0 or i == len(videos):
                    await status_msg.edit_text(
                        f"🔄 Обработка Videos: {i}/{len(videos)}\n"
                        f"✅ Обновлено: {updated_count}\n"
                        f"⏭️ Пропущено: {skipped_count}\n"
                        f"❌ Ошибок: {failed_count}"
                    )
                
            except Exception as e:
                failed_count += 1
                failed_ids.append(f"V:{video_id}:{str(e)[:20]}")
                print(f"❌ Ошибка для Videos {video_id}: {e}")
        
        # Обрабатываем PendingVideos
        for i, video in enumerate(pending, 1):
            video_id = str(video.get('id', ''))
            if not video_id:
                continue
            
            try:
                hashtags = await extract_hashtags_from_youtube(video_id)
                
                if hashtags is not None:
                    result = apps_script_request('update-hashtags', 'PUT', {
                        'sheet_name': 'PendingVideos',
                        'id': video_id,
                        'hashtags': hashtags
                    })
                    
                    if isinstance(result, dict) and result.get('success'):
                        updated_count += 1
                    else:
                        failed_count += 1
                        failed_ids.append(f"P:{video_id}")
                else:
                    skipped_count += 1
                
                # Обновляем прогресс
                progress = len(videos) + i
                if i % 5 == 0 or i == len(pending):
                    await status_msg.edit_text(
                        f"🔄 Обработка Pending: {i}/{len(pending)}\n"
                        f"✅ Обновлено: {updated_count}\n"
                        f"⏭️ Пропущено: {skipped_count}\n"
                        f"❌ Ошибок: {failed_count}"
                    )
                
            except Exception as e:
                failed_count += 1
                failed_ids.append(f"P:{video_id}:{str(e)[:20]}")
                print(f"❌ Ошибка для Pending {video_id}: {e}")
        
        # Итоговый отчёт
        report = f"✅ Обработка завершена!\n\n"
        report += f"📊 Статистика:\n"
        report += f"• Всего видео: {total}\n"
        report += f"• Обновлено: {updated_count}\n"
        report += f"• Пропущено (нет описания): {skipped_count}\n"
        report += f"• Ошибок: {failed_count}\n"
        
        if failed_ids:
            report += f"\n Ошибки (первые 10):\n"
            for fail in failed_ids[:10]:
                report += f"• {fail}\n"
            if len(failed_ids) > 10:
                report += f"... и ещё {len(failed_ids) - 10}\n"
        
        report += f"\n⚠️ Не забудь удалить функцию fix_hashtags_command из кода!"
        
        await status_msg.edit_text(report)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Критическая ошибка: {str(e)}")
        print(f"❌ Критическая ошибка fix_hashtags: {e}")


async def extract_hashtags_from_youtube(video_id: str) -> str:
    """Извлекает хэштеги из описания видео YouTube. Возвращает строку или None."""
    try:
        if not YOUTUBE_API_KEY:
            return None
        
        api_url = f'https://www.googleapis.com/youtube/v3/videos'
        api_response = requests.get(
            api_url,
            params={
                'part': 'snippet',
                'id': video_id,
                'key': YOUTUBE_API_KEY
            },
            timeout=10
        )
        api_data = api_response.json()
        
        if not api_data.get('items'):
            return None
        
        snippet = api_data['items'][0].get('snippet', {})
        description = snippet.get('description', '')
        
        if not description:
            return None
        
        # Ищем хэштеги (включая корейские символы)
        hashtag_pattern = r'#([a-zA-Z0-9_가-힣]+)'
        found_tags = re.findall(hashtag_pattern, description)
        
        if not found_tags:
            return None
        
        # Убираем дубликаты, добавляем #, ограничиваем до 15
        hashtags = list(dict.fromkeys([f'#{tag}' for tag in found_tags]))[:15]
        
        return ','.join(hashtags)
        
    except Exception as e:
        print(f"⚠️ Ошибка извлечения хэштегов для {video_id}: {e}")
        return None

async def fix_playlists_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Временная команда: обновляет динамические плейлисты для всех видео"""
    
    if not check_access(update.effective_user.id):
        return
    
    await update.message.reply_text(
        "⚠️ ВНИМАНИЕ: Это временная функция!\n\n"
        "Сейчас я пройдусь по всем видео в таблице Videos,\n"
        "проверю хэштеги и добавлю видео в динамические плейлисты.\n\n"
        "Это может занять несколько секунд. Начать?"
    )
    
    status_msg = await update.message.reply_text("🔄 Начинаю обработку...")
    
    try:
        result = apps_script_request('fix-playlists', 'GET')
        
        if isinstance(result, dict):
            if result.get('success'):
                report = f"✅ Обработка завершена!\n\n"
                report += f" Статистика:\n"
                report += f"• Обработано видео: {result.get('processedVideos', 0)}\n"
                report += f"• Добавлено в плейлисты: {result.get('updatedCount', 0)}\n"
                report += f"• Пропущено (нет хэштегов): {result.get('skippedCount', 0)}\n"
                report += f"\n⚠️ Не забудь удалить функцию fix_playlists_command из кода!"
                
                await status_msg.edit_text(report)
            else:
                await status_msg.edit_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
        else:
            await status_msg.edit_text(f" Неожиданный ответ от сервера")
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Критическая ошибка: {str(e)}")
        print(f"❌ Ошибка fix_playlists: {e}")

import asyncio
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters

async def handle_file_with_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка файла со списком YouTube ссылок (поддержка тысяч ссылок)"""
    
    file = None
    if update.message.document:
        file_name = update.message.document.file_name or ""
        file_ext = file_name.lower().split('.')[-1] if '.' in file_name else ''
        
        if file_ext not in ('txt', 'csv', 'log'):
            return
        
        file = await update.message.document.get_file()
    else:
        return
    
    if file.file_size > 2 * 1024 * 1024:
        await update.message.reply_text("❌ Файл слишком большой. Максимальный размер: 2 МБ")
        return
    
    try:
        status_msg = await update.message.reply_text("📥 Скачиваю и читаю файл...")
        
        file_bytes = await file.download_as_bytearray()
        file_text = file_bytes.decode('utf-8', errors='ignore')
        
        youtube_patterns = [
            r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/live/)([0-9A-Za-z_-]{11})',
            r'^([0-9A-Za-z_-]{11})$',
        ]
        
        lines = [line.strip() for line in file_text.split('\n') if line.strip()]
        video_ids = []
        unrecognized_lines = []
        
        for line in lines:
            found = False
            for pattern in youtube_patterns[:-1]:
                if re.search(pattern, line):
                    match = re.search(pattern, line)
                    video_ids.append(match.group(1))
                    found = True
                    break
            
            if not found and re.match(youtube_patterns[-1], line):
                video_ids.append(line)
                found = True
            
            if not found:
                unrecognized_lines.append(line)
        
        video_ids = list(set(video_ids))
        
        if not video_ids and not unrecognized_lines:
            await status_msg.edit_text("❌ Файл пуст или не содержит текста.")
            return
            
        if not video_ids and unrecognized_lines:
            # Создаём файл с нераспознанными строками
            error_file_content = "НЕРАСПОЗНАННЫЕ ССЫЛКИ\n"
            error_file_content += "=" * 50 + "\n\n"
            for line in unrecognized_lines:
                error_file_content += f"{line}\n"
            
            with open(f'unrecognized_{update.message.message_id}.txt', 'w', encoding='utf-8') as f:
                f.write(error_file_content)
            
            await update.message.reply_document(
                document=open(f'unrecognized_{update.message.message_id}.txt', 'rb'),
                filename=f'neraspoznanno_{len(unrecognized_lines)}.txt',
                caption=f"❌ Не удалось распознать ни одной ссылки!\n\nВсего нераспознанных строк: {len(unrecognized_lines)}"
            )
            
            import os
            os.remove(f'unrecognized_{update.message.message_id}.txt')
            return

        if len(video_ids) > 5000:
            await status_msg.edit_text("⚠️ Слишком много ссылок (>5000). Разбейте файл на части.")
            return

        await status_msg.edit_text(f" Найдено уникальных ссылок: {len(video_ids)}\nПроверяю существующие...")
        
        videos = apps_script_request('videos', 'GET')
        pending = apps_script_request('pending-videos', 'GET')
        
        existing_video_ids = set()
        if isinstance(videos, list):
            existing_video_ids.update([str(v.get('id', '')) for v in videos])
        if isinstance(pending, list):
            existing_video_ids.update([str(p.get('id', '')) for p in pending])
        
        new_video_ids = [vid for vid in video_ids if vid not in existing_video_ids]
        already_exist_count = len(video_ids) - len(new_video_ids)
        
        if not new_video_ids and not unrecognized_lines:
            await status_msg.edit_text(f"✅ Все {len(video_ids)} видео из файла уже есть в таблицах.")
            return
        
        await status_msg.edit_text(
            f"📊 Статистика файла:\n"
            f"• Всего строк: {len(lines)}\n"
            f"• Распознано: {len(video_ids)}\n"
            f"• Уже в таблицах: {already_exist_count}\n"
            f"• Будет обработано: {len(new_video_ids)}\n"
            f"• Нераспознано: {len(unrecognized_lines)}\n\n"
            f"🔄 Начинаю пакетную обработку..."
        )
        
        channels = apps_script_request('channels', 'GET')
        
        batch_size = 20
        total_batches = (len(new_video_ids) + batch_size - 1) // batch_size
        current_batch = 0
        added_total = 0
        failed_total = 0
        failed_links = []  # ← Все ссылки с ошибками
        
        for i in range(0, len(new_video_ids), batch_size):
            current_batch += 1
            batch_ids = new_video_ids[i:i + batch_size]
            batch_data = []
            
            for video_id in batch_ids:
                try:
                    oembed_url = f'https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json'
                    oembed_response = requests.get(oembed_url, timeout=10)
                    
                    if oembed_response.status_code != 200:
                        failed_total += 1
                        failed_links.append({
                            'url': f'https://youtu.be/{video_id}',
                            'reason': 'Нет доступа (удалено/приватное)'
                        })
                        continue
                    
                    oembed_data = oembed_response.json()
                    channel_id = 'manual'
                    channel_name = oembed_data.get('author_name', 'Неизвестно')
                    duration = ''
                    published_at = ''
                    hashtags = []
                    
                    if YOUTUBE_API_KEY:
                        try:
                            api_url = f'https://www.googleapis.com/youtube/v3/videos'
                            api_response = requests.get(
                                api_url,
                                params={'part': 'snippet,contentDetails,liveStreamingDetails', 'id': video_id, 'key': YOUTUBE_API_KEY},
                                timeout=10
                            )
                            api_data = api_response.json()
                            
                            if not api_data.get('items'):
                                failed_total += 1
                                failed_links.append({
                                    'url': f'https://youtu.be/{video_id}',
                                    'reason': 'Видео не найдено в API'
                                })
                                continue
                            
                            video_info = api_data['items'][0]
                            snippet = video_info['snippet']
                            yt_channel_id = snippet.get('channelId', '')
                            
                            if 'description' in snippet:
                                found_tags = re.findall(r'#([a-zA-Z0-9_가-힣]+)', snippet.get('description', ''))
                                hashtags = list(dict.fromkeys([f'#{tag}' for tag in found_tags]))[:15]
                            
                            pub_iso = snippet.get('publishedAt', '')
                            if pub_iso:
                                published_at = datetime.fromisoformat(pub_iso.replace('Z', '+00:00')).strftime('%d.%m.%Y')
                            
                            dur_iso = video_info['contentDetails']['duration']
                            if dur_iso:
                                h = int(re.search(r'(\d+)H', dur_iso).group(1)) if re.search(r'(\d+)H', dur_iso) else 0
                                m = int(re.search(r'(\d+)M', dur_iso).group(1)) if re.search(r'(\d+)M', dur_iso) else 0
                                s = int(re.search(r'(\d+)S', dur_iso).group(1)) if re.search(r'(\d+)S', dur_iso) else 0
                                duration = f'{h}:{m:02d}:{s:02d}' if h > 0 else f'{m}:{s:02d}'
                            else:
                                duration = 'LIVE'
                            
                            if isinstance(channels, list):
                                for ch in channels:
                                    ch_url = str(ch.get('url', '')).strip()
                                    if ch_url == yt_channel_id or f'youtube.com/channel/{yt_channel_id}' in ch_url:
                                        channel_id = ch.get('id', 'manual')
                                        channel_name = ch.get('name', channel_name)
                                        break
                                if channel_id == 'manual':
                                    oembed_name_lower = channel_name.lower().strip()
                                    for ch in channels:
                                        db_name = str(ch.get('name', '')).lower().strip()
                                        if db_name == oembed_name_lower or db_name in oembed_name_lower or oembed_name_lower in db_name:
                                            channel_id = ch.get('id', 'manual')
                                            channel_name = ch.get('name', channel_name)
                                            break
                        except Exception as e:
                            failed_total += 1
                            failed_links.append({
                                'url': f'https://youtu.be/{video_id}',
                                'reason': f'Ошибка API: {str(e)[:50]}'
                            })
                            continue
                    else:
                        failed_total += 1
                        failed_links.append({
                            'url': f'https://youtu.be/{video_id}',
                            'reason': 'Не указан YouTube API ключ'
                        })
                        continue
                    
                    batch_data.append({
                        'id': video_id,
                        'title': oembed_data.get('title', 'Без названия'),
                        'channel_id': channel_id,
                        'channel_name': channel_name,
                        'published_at': published_at,
                        'duration': duration,
                        'hashtags': ','.join(hashtags),
                        'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/hqdefault.jpg',
                        'video_url': f'https://youtube.com/watch?v={video_id}'
                    })
                    
                except Exception as e:
                    failed_total += 1
                    failed_links.append({
                        'url': f'https://youtu.be/{video_id}',
                        'reason': f'Неизвестная ошибка: {str(e)[:50]}'
                    })
            
            if batch_data:
                try:
                    result = apps_script_request('batch-pending-videos', 'POST', {'videos': batch_data})
                    if isinstance(result, dict) and result.get('success'):
                        added_total += result.get('added', len(batch_data))
                    else:
                        failed_total += len(batch_data)
                        for vid in batch_ids:
                            failed_links.append({
                                'url': f'https://youtu.be/{vid}',
                                'reason': 'Ошибка Apps Script'
                            })
                except Exception as e:
                    failed_total += len(batch_data)
                    for vid in batch_ids:
                        failed_links.append({
                            'url': f'https://youtu.be/{vid}',
                            'reason': f'Ошибка отправки: {str(e)[:30]}'
                        })
                    print(f"❌ Ошибка пакетной отправки: {e}")
            
            progress_pct = int((current_batch / total_batches) * 100)
            bar_len = 20
            filled = int(bar_len * current_batch / total_batches)
            bar = '█' * filled + '░' * (bar_len - filled)
            
            await status_msg.edit_text(
                f"🔄 Обработка: {progress_pct}%\n"
                f"[{bar}]\n"
                f"Пакет {current_batch}/{total_batches}\n"
                f"✅ Добавлено: {added_total}\n"
                f"❌ Ошибок: {failed_total}"
            )
            
            if current_batch < total_batches:
                await asyncio.sleep(1.5)
        
        # Создаём файл с ошибками и нераспознанными ссылками
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'errors_{timestamp}.txt'
        
        error_file_content = "ОТЧЁТ ОБ ОБРАБОТКЕ ФАЙЛА\n"
        error_file_content += "=" * 50 + "\n\n"
        error_file_content += f"Всего строк в файле: {len(lines)}\n"
        error_file_content += f"Распознано ссылок: {len(video_ids)}\n"
        error_file_content += f"Уже было в таблицах: {already_exist_count}\n"
        error_file_content += f"Успешно добавлено: {added_total}\n"
        error_file_content += f"Ошибок обработки: {failed_total}\n"
        error_file_content += f"Нераспознанных строк: {len(unrecognized_lines)}\n\n"
        
        if unrecognized_lines:
            error_file_content += "=" * 50 + "\n"
            error_file_content += "НЕРАСПОЗНАННЫЕ ССЫЛКИ\n"
            error_file_content += "=" * 50 + "\n\n"
            for line in unrecognized_lines:
                error_file_content += f"{line}\n"
            error_file_content += "\n"
        
        if failed_links:
            error_file_content += "=" * 50 + "\n"
            error_file_content += "ССЫЛКИ С ОШИБКАМИ ОБРАБОТКИ\n"
            error_file_content += "=" * 50 + "\n\n"
            for fail in failed_links:
                error_file_content += f"{fail['url']} — {fail['reason']}\n"
        
        # Записываем файл
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(error_file_content)
        
        # Отправляем файл пользователю
        caption = f"✅ Обработка завершена!\n\n"
        caption += f"📊 Итоги:\n"
        caption += f"• Распознано: {len(video_ids)}\n"
        caption += f"• Уже было: {already_exist_count}\n"
        caption += f"• Добавлено: {added_total}\n"
        caption += f"• Ошибок: {failed_total}\n"
        caption += f"• Нераспознано: {len(unrecognized_lines)}\n\n"
        
        if failed_total > 0 or len(unrecognized_lines) > 0:
            caption += f"📎 Все проблемные ссылки в прикреплённом файле"
        
        await update.message.reply_document(
            document=open(filename, 'rb'),
            filename=filename,
            caption=caption
        )
        
        # Удаляем временный файл
        import os
        os.remove(filename)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Критическая ошибка обработки файла: {str(e)}")
        print(f"❌ Ошибка файла: {e}")
        
async def fix_pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для очистки PendingVideos от дубликатов, которые уже есть в Videos"""
    
    if not check_access(update.effective_user.id):
        return
    
    status_msg = await update.message.reply_text("🔄 Сканирую таблицы на наличие дубликатов...")
    
    try:
        result = apps_script_request('fix-pending-duplicates', 'POST')
        
        if isinstance(result, dict) and result.get('success'):
            deleted = result.get('deleted', 0)
            await status_msg.edit_text(
                f"✅ Готово!\n\n"
                f"🗑 Удалено дубликатов из Pending: **{deleted}**\n"
                f"Теперь в списке 'Новые видео' остались только уникальные записи."
            )
        else:
            await status_msg.edit_text(f"❌ Ошибка: {result.get('error', 'Неизвестная ошибка')}")
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Критическая ошибка: {str(e)}")
        print(f"❌ Ошибка fix_pending: {e}")
        
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр последних логов приложения"""
    
    if not check_access(update.effective_user.id):
        return
    
    status_msg = await update.message.reply_text("📋 Загружаю логи...")
    
    try:
        result = apps_script_request('get-logs', 'GET')
        
        if not isinstance(result, dict) or not result.get('logs'):
            await status_msg.edit_text("✅ Логов нет. Всё работает отлично!")
            return
        
        logs = result.get('logs', [])
        
        msg = f"📋 Последние логи ({len(logs)} записей):\n\n"
        
        # Показываем только ошибки и критические
        error_logs = [log for log in logs if log.get('type') in ['error', 'critical', 'promise_error']]
        
        if not error_logs:
            msg += "✅ Ошибок не найдено!\n\n"
        else:
            msg += f" Ошибки ({len(error_logs)}):\n\n"
            for log in error_logs[:10]:
                timestamp = log.get('timestamp', '')[:16].replace('T', ' ')
                msg_type = log.get('type', '')
                message = log.get('message', '')[:100]
                
                msg += f"• [{timestamp}] {msg_type}\n"
                msg += f"  {message}\n\n"
        
        # Последние 5 записей всех типов
        msg += f"📝 Последние записи:\n\n"
        for log in logs[:5]:
            timestamp = log.get('timestamp', '')[:16].replace('T', ' ')
            msg_type = log.get('type', '')
            message = log.get('message', '')[:80]
            
            msg += f"[{timestamp}] {msg_type}: {message}\n"
        
        await status_msg.edit_text(msg)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Ошибка загрузки логов: {str(e)}")

async def health_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверка доступности сервиса"""
    
    if not check_access(update.effective_user.id):
        return
    
    status_msg = await update.message.reply_text("🔍 Проверяю доступность сервиса...")
    
    try:
        start_time = time.time()
        result = apps_script_request('health', 'GET')
        response_time = int((time.time() - start_time) * 1000)
        
        if isinstance(result, dict) and result.get('status') == 'ok':
            await status_msg.edit_text(
                f"✅ Сервис доступен!\n\n"
                f"⏱ Время ответа: {response_time} мс\n"
                f"🕐 Серверное время: {result.get('timestamp', 'N/A')[:19].replace('T', ' ')}"
            )
        else:
            await status_msg.edit_text(f"⚠️ Сервис ответил странно: {result}")
            
    except Exception as e:
        await status_msg.edit_text(
            f"❌ Сервис недоступен!\n\n"
            f"Ошибка: {str(e)}\n\n"
            f"Возможно, Apps Script упал или превышен лимит запросов."
        )
    # Автоматическая проверка доступности раз в час
    async def periodic_health_check(context):
        try:
            result = apps_script_request('health', 'GET')
            
            if not isinstance(result, dict) or result.get('status') != 'ok':
                # Сервис недоступен - отправляем уведомление админу
                admin_id = ADMIN_ID  # Замени на свой ID
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=f"⚠️ ВНИМАНИЕ: Сервис недоступен!\n\n"
                         f"Последняя проверка: {datetime.now().strftime('%H:%M:%S')}\n"
                         f"Ответ: {result}"
                )
        except Exception as e:
            admin_id = ADMIN_ID
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Сервис не отвечает!\n\n"
                     f"Ошибка: {str(e)}"
            )
    
    # Запускаем проверку раз в час (3600 секунд)
    context = application.create_application_callback_context()
    application.job_queue.run_repeating(periodic_health_check, interval=3600*12, first=60)
# ===== ЗАПУСК =====
def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("app", app_command))
    application.add_handler(CommandHandler("channels", channels_command))
    application.add_handler(CommandHandler("addchannel", add_channel_command))
    application.add_handler(CommandHandler("track", track_command))
    application.add_handler(CommandHandler("untrack", untrack_command))
    application.add_handler(CommandHandler("settype", set_type_command))
    application.add_handler(CommandHandler("refresh", refresh_command))
    application.add_handler(CommandHandler("pending", pending_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("addcat", add_category_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("fix_hashtags", fix_hashtags_command))
    application.add_handler(CommandHandler("fix_playlists", fix_playlists_command))
    application.add_handler(CommandHandler("fix_pending", fix_pending_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("health", health_check_command))
    # Обработка файлов со ссылками (ПЕРЕД текстовым хендлером!)
    application.add_handler(MessageHandler(
        filters.Document.ALL,
        handle_file_with_links
    ))
    
    # Обработка ссылок в тексте (после файлов)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_youtube_link
    ))
    
    print("🤖 Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
