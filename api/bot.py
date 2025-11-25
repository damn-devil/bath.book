import logging
from datetime import datetime, timedelta, date
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler, 
    MessageHandler, 
    Filters, 
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler
)
import sqlite3
import os
import asyncio
from flask import Flask, request, jsonify

# Настройка логирования
logging.basicConfig(
    format='%(asasctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
GENDER, PLACES, TIME, CONFIRMATION = range(4)

# Глобальные переменные для бота
application = None
BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

# Инициализация базы данных
def init_db():
    # На Vercel используем временную базу в памяти или файловую систему
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            gender TEXT
        )
    ''')
    
    # Таблица бронирований
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
    
    # Таблица для отслеживания текущего дня
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

# Функция для проверки и очистки старых данных
def check_and_clear_old_data():
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT current_date FROM current_day WHERE id = 1')
    result = cursor.fetchone()
    
    if result:
        stored_date = date.fromisoformat(result[0])
        today = date.today()
        
        if stored_date < today:
            cursor.execute('DELETE FROM bookings')
            cursor.execute('UPDATE current_day SET current_date = ? WHERE id = 1', 
                          (today.isoformat(),))
            conn.commit()
            logger.info("Бронирования очищены для нового дня")
    
    conn.close()

# Команда /start
async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    user_id = user.id
    
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    if not cursor.fetchone():
        cursor.execute('INSERT INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)',
                      (user_id, user.username, user.first_name, user.last_name))
        conn.commit()
    conn.close()
    
    check_and_clear_old_data()
    
    await update.message.reply_text(
        f'Привет, {user.first_name}! Я бот для бронирования душа в общежитии.\n\n'
        'Доступные команды:\n'
        '/book - Забронировать время\n'
        '/my_bookings - Мои бронирования\n'
        '/cancel - Отменить бронирование\n'
        '/schedule - Посмотреть расписание на сегодня'
    )

# Начало процесса бронирования
async def book(update: Update, context: CallbackContext) -> int:
    reply_keyboard = [['Мужской', 'Женский']]
    
    await update.message.reply_text(
        'Выберите пол:',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, 
            one_time_keyboard=True,
            input_field_placeholder='Мужской или Женский?'
        ),
    )
    
    return GENDER

# Обработка выбора пола
async def gender(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    gender = update.message.text
    
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET gender = ? WHERE user_id = ?', (gender, user.id))
    conn.commit()
    conn.close()
    
    context.user_data['gender'] = gender
    
    reply_keyboard = [['1', '2']]
    
    await update.message.reply_text(
        'На сколько мест бронируете?',
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, 
            one_time_keyboard=True,
            input_field_placeholder='1 или 2?'
        ),
    )
    
    return PLACES

# Обработка выбора количества мест
async def places(update: Update, context: CallbackContext) -> int:
    places = int(update.message.text)
    context.user_data['places'] = places
    
    await update.message.reply_text(
        'На какое время хотите забронировать? (В формате ЧЧ:MM, например 14:30)\n'
        'Максимальное время брони - 30 минут.',
        reply_markup=ReplyKeyboardRemove()
    )
    
    return TIME

# Проверка доступности времени
def is_time_available(gender: str, places: int, start_time: datetime, end_time: datetime) -> bool:
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT start_time, end_time, places FROM bookings 
        WHERE gender = ? AND booking_date = ?
    ''', (gender, date.today().isoformat()))
    
    bookings = cursor.fetchall()
    conn.close()
    
    for booking in bookings:
        booking_start = datetime.strptime(booking[0], '%H:%M').time()
        booking_end = datetime.strptime(booking[1], '%H:%M').time()
        booking_places = booking[2]
        
        if not (end_time.time() <= booking_start or start_time.time() >= booking_end):
            total_places_used = sum(b[2] for b in bookings 
                                  if not (end_time.time() <= datetime.strptime(b[0], '%H:%M').time() or 
                                         start_time.time() >= datetime.strptime(b[1], '%H:%M').time()))
            
            if total_places_used + places > 2:
                return False
    
    return True

# Обработка выбора времени
async def time(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    time_str = update.message.text
    
    try:
        start_time = datetime.strptime(time_str, '%H:%M')
        end_time = start_time + timedelta(minutes=30)
        
        if start_time.time() < datetime.strptime('00:00', '%H:%M').time() or end_time.time() > datetime.strptime('23:59', '%H:%M').time():
            await update.message.reply_text('Время должно быть между 00:00 и 23:30')
            return TIME
            
    except ValueError:
        await update.message.reply_text('Пожалуйста, введите время в правильном формате (ЧЧ:MM)')
        return TIME
    
    gender = context.user_data['gender']
    places = context.user_data['places']
    
    if is_time_available(gender, places, start_time, end_time):
        context.user_data['start_time'] = start_time.strftime('%H:%M')
        context.user_data['end_time'] = end_time.strftime('%H:%M')
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data='confirm')],
            [InlineKeyboardButton("❌ Отменить", callback_data='cancel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'Подтвердите бронирование:\n\n'
            f'Пол: {gender}\n'
            f'Мест: {places}\n'
            f'Время: {context.user_data["start_time"]} - {context.user_data["end_time"]}',
            reply_markup=reply_markup
        )
        
        return CONFIRMATION
    else:
        await update.message.reply_text(
            'К сожалению, на это время нет свободных мест. Пожалуйста, выберите другое время.'
        )
        return TIME

# Обработка подтверждения
async def confirmation(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm':
        user_id = query.from_user.id
        gender = context.user_data['gender']
        places = context.user_data['places']
        start_time = context.user_data['start_time']
        end_time = context.user_data['end_time']
        
        conn = sqlite3.connect('/tmp/shower_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bookings (user_id, gender, places, start_time, end_time, booking_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, gender, places, start_time, end_time, date.today().isoformat()))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f'✅ Бронирование подтверждено!\n\n'
            f'Пол: {gender}\n'
            f'Мест: {places}\n'
            f'Время: {start_time} - {end_time}'
        )
    else:
        await query.edit_message_text('❌ Бронирование отменено.')
    
    return ConversationHandler.END

# Показать расписание
async def schedule(update: Update, context: CallbackContext) -> None:
    check_and_clear_old_data()
    
    conn = sqlite3.connect('/tmp/shower_bot.db')
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
        await update.message.reply_text('На сегодня бронирований нет.')
        return
    
    schedule_text = "📅 Расписание на сегодня:\n\n"
    
    for booking in bookings:
        name, gender, places, start, end = booking
        schedule_text += f"👤 {name} ({gender})\n"
        schedule_text += f"📍 Мест: {places}\n"
        schedule_text += f"🕐 {start} - {end}\n"
        schedule_text += "─" * 20 + "\n"
    
    await update.message.reply_text(schedule_text)

# Показать мои бронирования
async def my_bookings(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    check_and_clear_old_data()
    
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
        await update.message.reply_text('У вас нет бронирований на сегодня.')
        return
    
    bookings_text = "📋 Ваши бронирования на сегодня:\n\n"
    
    for i, booking in enumerate(bookings, 1):
        gender, places, start, end = booking
        bookings_text += f"{i}. {gender}, мест: {places}\n"
        bookings_text += f"   Время: {start} - {end}\n\n"
    
    await update.message.reply_text(bookings_text)

# Отмена бронирования
async def cancel_booking(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    check_and_clear_old_data()
    
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, gender, places, start_time, end_time 
        FROM bookings 
        WHERE user_id = ? AND booking_date = ?
        ORDER BY start_time
    ''', (user_id, date.today().isoformat()))
    
    bookings = cursor.fetchall()
    
    if not bookings:
        await update.message.reply_text('У вас нет бронирований для отмены.')
        conn.close()
        return
    
    keyboard = []
    for booking in bookings:
        booking_id, gender, places, start, end = booking
        keyboard.append([InlineKeyboardButton(
            f"{gender} | {places} мест | {start}-{end}", 
            callback_data=f"cancel_{booking_id}"
        )])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        'Выберите бронирование для отмены:',
        reply_markup=reply_markup
    )
    
    conn.close()

# Обработка отмены бронирования
async def cancel_booking_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    booking_id = int(query.data.split('_')[1])
    
    conn = sqlite3.connect('/tmp/shower_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text('✅ Бронирование отменено.')

# Отмена диалога
async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        'Бронирование отменено.',
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# Инициализация бота
def setup_bot():
    global application
    
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN не установлен")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Инициализация базы данных
    init_db()
    
    # ConversationHandler для бронирования
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('book', book)],
        states={
            GENDER: [MessageHandler(Filters.regex('^(Мужской|Женский)$'), gender)],
            PLACES: [MessageHandler(Filters.regex('^(1|2)$'), places)],
            TIME: [MessageHandler(Filters.TEXT & ~Filters.COMMAND, time)],
            CONFIRMATION: [CallbackQueryHandler(confirmation)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("schedule", schedule))
    application.add_handler(CommandHandler("my_bookings", my_bookings))
    application.add_handler(CommandHandler("cancel", cancel_booking))
    application.add_handler(CallbackQueryHandler(cancel_booking_handler, pattern='^cancel_'))
    
    return application