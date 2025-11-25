from http.server import BaseHTTPRequestHandler
import json
import os
from datetime import datetime, timedelta, date
import sqlite3
import asyncio

# Имитируем необходимые классы из python-telegram-bot
class Update:
    def __init__(self, update_data, bot=None):
        self.update_id = update_data.get('update_id')
        self.message = Message(update_data.get('message')) if 'message' in update_data else None
        self.callback_query = CallbackQuery(update_data.get('callback_query')) if 'callback_query' in update_data else None
    
    @classmethod
    def de_json(cls, data, bot):
        return cls(data)

class Message:
    def __init__(self, message_data):
        if message_data:
            self.message_id = message_data.get('message_id')
            self.from_user = User(message_data.get('from'))
            self.chat = Chat(message_data.get('chat'))
            self.text = message_data.get('text')
            self.date = message_data.get('date')

class User:
    def __init__(self, user_data):
        if user_data:
            self.id = user_data.get('id')
            self.username = user_data.get('username')
            self.first_name = user_data.get('first_name')
            self.last_name = user_data.get('last_name')

class Chat:
    def __init__(self, chat_data):
        if chat_data:
            self.id = chat_data.get('id')

class CallbackQuery:
    def __init__(self, callback_data):
        if callback_data:
            self.id = callback_data.get('id')
            self.from_user = User(callback_data.get('from'))
            self.data = callback_data.get('data')
            self.message = Message(callback_data.get('message'))

class Bot:
    def __init__(self, token):
        self.token = token
    
    async def send_message(self, chat_id, text, reply_markup=None):
        # В реальной реализации здесь будет вызов Telegram API
        print(f"Send to {chat_id}: {text}")
        return True
    
    async def answer_callback_query(self, callback_query_id):
        print(f"Answer callback: {callback_query_id}")
        return True
    
    async def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        print(f"Edit message {message_id} in {chat_id}: {text}")
        return True

class Application:
    def __init__(self, bot):
        self.bot = bot
        self.handlers = {}
    
    def add_handler(self, handler):
        # Упрощенная обработка хендлеров
        pass
    
    async def process_update(self, update):
        if update.message and update.message.text:
            await self.handle_message(update.message)
        elif update.callback_query:
            await self.handle_callback(update.callback_query)
    
    async def handle_message(self, message):
        text = message.text
        user_id = message.from_user.id
        
        if text.startswith('/start'):
            await self.bot.send_message(user_id, 
                "Привет! Я бот для бронирования душа в общежитии.\n\n"
                "Доступные команды:\n"
                "/book - Забронировать время\n"
                "/my_bookings - Мои бронирования\n"
                "/cancel - Отменить бронирование\n"
                "/schedule - Посмотреть расписание на сегодня"
            )
        elif text.startswith('/schedule'):
            await self.show_schedule(user_id)
        elif text.startswith('/my_bookings'):
            await self.show_my_bookings(user_id, message.from_user)
        elif text.startswith('/book'):
            await self.start_booking(user_id)
        elif text.startswith('/cancel'):
            await self.cancel_booking(user_id)
    
    async def handle_callback(self, callback_query):
        await self.bot.answer_callback_query(callback_query.id)
        user_id = callback_query.from_user.id
        
        if callback_query.data.startswith('confirm_booking'):
            await self.confirm_booking(user_id, callback_query)
        elif callback_query.data.startswith('cancel_booking'):
            await self.bot.edit_message_text(user_id, callback_query.message.message_id, "❌ Бронирование отменено.")
    
    async def show_schedule(self, chat_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.first_name, b.gender, b.places, b.start_time, b.end_time 
            FROM bookings b
            JOIN users u ON b.user_id = u.user_id
            WHERE b.booking_date = ?
            ORDER BY b.start_time
        ''', (date.today().isoformat(),))
        
        bookings = cursor.fetchall()
        conn.close()
        
        if not bookings:
            await self.bot.send_message(chat_id, 'На сегодня бронирований нет.')
            return
        
        schedule_text = "📅 Расписание на сегодня:\n\n"
        
        for booking in bookings:
            name, gender, places, start, end = booking
            schedule_text += f"👤 {name} ({gender})\n"
            schedule_text += f"📍 Мест: {places}\n"
            schedule_text += f"🕐 {start} - {end}\n"
            schedule_text += "─" * 20 + "\n"
        
        await self.bot.send_message(chat_id, schedule_text)
    
    async def show_my_bookings(self, chat_id, user):
        user_id = user.id
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT gender, places, start_time, end_time 
            FROM bookings 
            WHERE user_id = ? AND booking_date = ?
            ORDER BY start_time
        ''', (user_id, date.today().isoformat()))
        
        bookings = cursor.fetchall()
        conn.close()
        
        if not bookings:
            await self.bot.send_message(chat_id, 'У вас нет бронирований на сегодня.')
            return
        
        bookings_text = "📋 Ваши бронирования на сегодня:\n\n"
        
        for i, booking in enumerate(bookings, 1):
            gender, places, start, end = booking
            bookings_text += f"{i}. {gender}, мест: {places}\n"
            bookings_text += f"   Время: {start} - {end}\n\n"
        
        await self.bot.send_message(chat_id, bookings_text)
    
    async def start_booking(self, chat_id):
        await self.bot.send_message(chat_id,
            "Начнем бронирование!\n\n"
            "Выберите пол, отправив:\n"
            "👨 Мужской\n"
            "👩 Женский"
        )
    
    async def confirm_booking(self, chat_id, callback_query):
        await self.bot.edit_message_text(
            chat_id, 
            callback_query.message.message_id,
            "✅ Бронирование подтверждено!\n\n"
            "Пол: Мужской\n"
            "Мест: 1\n"
            "Время: 14:00 - 14:30"
        )

# Инициализация базы данных
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            gender TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            gender TEXT,
            places INTEGER,
            start_time TEXT,
            end_time TEXT,
            booking_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS current_day (
            id INTEGER PRIMARY KEY,
            current_date TEXT
        )
    ''')
    
    cursor.execute('SELECT * FROM current_day WHERE id = 1')
    if not cursor.fetchone():
        cursor.execute('INSERT INTO current_day (id, current_date) VALUES (1, ?)', 
                      (date.today().isoformat(),))
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Получение соединения с базой данных"""
    return sqlite3.connect('/tmp/shower_bot.db')

# Глобальные переменные
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
bot = None
application = None

def setup_bot():
    global bot, application
    
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    
    bot = Bot(BOT_TOKEN)
    application = Application(bot)
    
    # Инициализация базы данных
    init_db()
    
    return application

class Handler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if self.path == '/api/set-webhook':
            self.set_webhook()
        elif self.path == '/':
            self.send_home()
        else:
            self.send_error(404)
    
    def do_POST(self):
        if self.path == '/api/webhook':
            self.handle_webhook()
        else:
            self.send_error(404)
    
    def set_webhook(self):
        try:
            webhook_url = f"https://{self.headers.get('Host')}/api/webhook"
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            response = {
                "status": "webhook set successfully",
                "url": webhook_url
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def handle_webhook(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            update_data = json.loads(post_data.decode())
            
            # Создаем объект Update
            update = Update(update_data)
            
            # Обрабатываем обновление
            asyncio.run(application.process_update(update))
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            
        except Exception as e:
            print(f"Error: {e}")
            self.send_error(500, str(e))
    
    def send_home(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        
        response = {
            "status": "Bot is running",
            "service": "Telegram Shower Booking Bot",
            "endpoints": {
                "GET /": "This page",
                "GET /api/set-webhook": "Set Telegram webhook",
                "POST /api/webhook": "Telegram webhook endpoint"
            }
        }
        
        self.wfile.write(json.dumps(response, indent=2).encode())

# Инициализация при импорте
setup_bot()

# Функция для Vercel
def app(request):
    return Handler()
