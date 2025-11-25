from http.server import BaseHTTPRequestHandler
import json
import os
import sqlite3
from datetime import datetime, date
import requests
import sys

# Перенаправляем stdout для логирования в Vercel
sys.stdout.flush()

class Handler(BaseHTTPRequestHandler):
    
    def log_message(self, format, *args):
        # Переопределяем логирование чтобы видеть в Vercel
        message = format % args
        print(f"🌐 {self.command} {self.path} - {message}")
        sys.stdout.flush()
    
    def do_GET(self):
        print(f"📨 GET request to: {self.path}")
        sys.stdout.flush()
        
        if self.path == '/api/set-webhook':
            self.set_webhook()
        elif self.path == '/api/test':
            self.test_endpoint()
        elif self.path == '/':
            self.home()
        else:
            print(f"❌ 404 for: {self.path}")
            sys.stdout.flush()
            self.send_error(404)
    
    def do_POST(self):
        print(f"📨 POST request to: {self.path}")
        sys.stdout.flush()
        
        if self.path == '/api/webhook':
            self.handle_webhook()
        else:
            print(f"❌ 404 for: {self.path}")
            sys.stdout.flush()
            self.send_error(404)
    
    def set_webhook(self):
        try:
            print("🔄 Setting webhook...")
            sys.stdout.flush()
            
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not token:
                print("❌ TELEGRAM_BOT_TOKEN not set")
                sys.stdout.flush()
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "TELEGRAM_BOT_TOKEN not set"}).encode())
                return
            
            host = self.headers.get('Host')
            webhook_url = f"https://{host}/api/webhook"
            
            print(f"🔗 Webhook URL: {webhook_url}")
            sys.stdout.flush()
            
            response = requests.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": webhook_url},
                timeout=10
            )
            
            result = response.json()
            print(f"📡 Telegram response: {result}")
            sys.stdout.flush()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "webhook_url": webhook_url,
                "telegram_response": result
            }).encode())
            
        except Exception as e:
            print(f"❌ Set webhook error: {e}")
            sys.stdout.flush()
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def handle_webhook(self):
        try:
            print("🤖 Webhook called by Telegram")
            sys.stdout.flush()
            
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode('utf-8'))
            
            print(f"📩 Update received: {update}")
            sys.stdout.flush()
            
            # Обрабатываем сообщение
            if 'message' in update:
                self.process_message(update['message'])
            
            # Всегда возвращаем 200 для Telegram
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode())
            
            print("✅ Webhook processed successfully")
            sys.stdout.flush()
            
        except Exception as e:
            print(f"❌ Webhook error: {e}")
            sys.stdout.flush()
            self.send_response(200)  # Всегда 200 для Telegram
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode())
    
    def process_message(self, message):
        """Обрабатывает сообщение от пользователя"""
        try:
            text = message.get('text', '')
            chat_id = message['chat']['id']
            user_id = message['from']['id']
            user_name = message['from'].get('first_name', 'User')
            
            print(f"👤 Message from {user_name} ({user_id}): {text}")
            sys.stdout.flush()
            
            # Инициализируем базу
            self.init_db()
            
            if text.startswith('/start'):
                response_text = (
                    f"Привет, {user_name}! 🚿\n\n"
                    "Я бот для бронирования душа в общежитии.\n\n"
                    "Доступные команды:\n"
                    "/book - Забронировать время\n"
                    "/my_bookings - Мои бронирования\n" 
                    "/cancel - Отменить бронирование\n"
                    "/schedule - Расписание на сегодня"
                )
                self.send_telegram_message(chat_id, response_text)
                
            elif text.startswith('/schedule'):
                self.show_schedule(chat_id)
                
            elif text.startswith('/my_bookings'):
                self.show_my_bookings(chat_id, user_id)
                
            elif text.startswith('/book'):
                self.send_telegram_message(chat_id,
                    "Для бронирования времени отправьте:\n\n"
                    "1. Пол (Мужской/Женский)\n"
                    "2. Количество мест (1 или 2)\n"
                    "3. Время (например, 14:30)\n\n"
                    "Пример: Мужской 1 14:30"
                )
                
            elif text.startswith('/cancel'):
                self.cancel_bookings(chat_id, user_id)
                
            else:
                self.send_telegram_message(chat_id, 
                    "Не понимаю команду. Используйте /start для списка команд."
                )
                
        except Exception as e:
            print(f"❌ Process message error: {e}")
            sys.stdout.flush()
    
    def send_telegram_message(self, chat_id, text):
        """Отправляет сообщение через Telegram API"""
        try:
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            if not token:
                print("❌ TELEGRAM_BOT_TOKEN not set")
                return
            
            print(f"📤 Sending message to {chat_id}: {text[:50]}...")
            sys.stdout.flush()
            
            response = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text
                },
                timeout=10
            )
            
            result = response.json()
            if response.status_code == 200 and result.get('ok'):
                print(f"✅ Message sent to {chat_id}")
            else:
                print(f"❌ Failed to send message: {result}")
                
            sys.stdout.flush()
            return result
            
        except Exception as e:
            print(f"❌ Send message error: {e}")
            sys.stdout.flush()
    
    # ... остальные методы (init_db, show_schedule, etc.) остаются без изменений ...
    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect('/tmp/shower_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bookings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    user_name TEXT,
                    gender TEXT,
                    places INTEGER,
                    start_time TEXT,
                    end_time TEXT,
                    booking_date TEXT
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
            print("✅ Database initialized")
            sys.stdout.flush()
        except Exception as e:
            print(f"❌ Database init error: {e}")
            sys.stdout.flush()
    
    def show_schedule(self, chat_id):
        """Показывает расписание"""
        try:
            conn = sqlite3.connect('/tmp/shower_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT user_name, gender, places, start_time, end_time 
                FROM bookings 
                WHERE booking_date = ?
                ORDER BY start_time
            ''', (date.today().isoformat(),))
            
            bookings = cursor.fetchall()
            conn.close()
            
            if not bookings:
                self.send_telegram_message(chat_id, '📅 На сегодня бронирований нет.')
                return
            
            schedule_text = "📅 Расписание на сегодня:\n\n"
            
            for booking in bookings:
                name, gender, places, start, end = booking
                schedule_text += f"👤 {name} ({gender})\n"
                schedule_text += f"📍 Мест: {places}\n"
                schedule_text += f"🕐 {start} - {end}\n"
                schedule_text += "─" * 20 + "\n"
            
            self.send_telegram_message(chat_id, schedule_text)
        except Exception as e:
            print(f"❌ Show schedule error: {e}")
            self.send_telegram_message(chat_id, "Ошибка при получении расписания.")
    
    def show_my_bookings(self, chat_id, user_id):
        """Показывает бронирования пользователя"""
        try:
            conn = sqlite3.connect('/tmp/shower_bot.db')
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
                self.send_telegram_message(chat_id, 'У вас нет бронирований на сегодня.')
                return
            
            bookings_text = "📋 Ваши бронирования:\n\n"
            
            for i, booking in enumerate(bookings, 1):
                gender, places, start, end = booking
                bookings_text += f"{i}. {gender}, мест: {places}\n"
                bookings_text += f"   Время: {start} - {end}\n\n"
            
            self.send_telegram_message(chat_id, bookings_text)
        except Exception as e:
            print(f"❌ Show my bookings error: {e}")
            self.send_telegram_message(chat_id, "Ошибка при получении бронирований.")
    
    def cancel_bookings(self, chat_id, user_id):
        """Отменяет все бронирования пользователя"""
        try:
            conn = sqlite3.connect('/tmp/shower_bot.db')
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM bookings 
                WHERE user_id = ? AND booking_date = ?
            ''', (user_id, date.today().isoformat()))
            
            conn.commit()
            conn.close()
            
            self.send_telegram_message(chat_id, "✅ Все ваши бронирования на сегодня отменены.")
        except Exception as e:
            print(f"❌ Cancel bookings error: {e}")
            self.send_telegram_message(chat_id, "Ошибка при отмене бронирований.")
    
    def test_endpoint(self):
        """Тестовый endpoint"""
        try:
            conn = sqlite3.connect('/tmp/shower_bot.db')
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            conn.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "tables": [table[0] for table in tables],
                "bot_token_set": bool(os.environ.get('TELEGRAM_BOT_TOKEN')),
                "timestamp": datetime.now().isoformat()
            }).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
    
    def home(self):
        """Главная страница"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "Bot is running!",
            "service": "Shower Booking Bot",
            "endpoints": {
                "GET /": "This page",
                "GET /api/set-webhook": "Set webhook",
                "GET /api/test": "Test endpoint",
                "POST /api/webhook": "Telegram webhook"
            }
        }).encode())

# Функция для Vercel
def app(request):
    return Handler()
