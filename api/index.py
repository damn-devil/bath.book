import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('shower_bot.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            gender TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            time TEXT NOT NULL,
            cabin_number INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect('shower_bot.db')

def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return {'user_id': user[0], 'gender': user[1], 'name': user[2]}
    return None

def save_user(user_id, gender, name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT OR REPLACE INTO users (user_id, gender, name) VALUES (?, ?, ?)',
        (user_id, gender, name)
    )
    conn.commit()
    conn.close()

def get_all_bookings():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT b.time, b.cabin_number, u.gender, u.name 
        FROM bookings b 
        JOIN users u ON b.user_id = u.user_id 
        ORDER BY b.time
    ''')
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def get_user_bookings(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, time, cabin_number 
        FROM bookings 
        WHERE user_id = ? 
        ORDER BY time
    ''', (user_id,))
    bookings = cursor.fetchall()
    conn.close()
    return bookings

def get_booking_owner(booking_id):
    """Получить user_id владельца бронирования"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM bookings WHERE id = ?', (booking_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def create_booking(user_id, time, cabin_number):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO bookings (user_id, time, cabin_number) VALUES (?, ?, ?)',
        (user_id, time, cabin_number)
    )
    conn.commit()
    conn.close()

def delete_booking(booking_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM bookings WHERE id = ?', (booking_id,))
    conn.commit()
    conn.close()

def cleanup_old_bookings():
    """Удаляет брони, время которых уже прошло"""
    conn = get_db_connection()
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%H:%M")
    
    # Удаляем брони, время которых меньше текущего времени
    cursor.execute('DELETE FROM bookings WHERE time < ?', (current_time,))
    deleted_count = cursor.rowcount
    
    conn.commit()
    conn.close()
    
    if deleted_count > 0:
        logging.info(f"Удалено {deleted_count} прошедших бронирований")
    
    return deleted_count

def check_availability(time, user_id):
    # Сначала очищаем старые брони
    cleanup_old_bookings()
    
    user = get_user(user_id)
    if not user:
        return 0
    
    bookings = get_all_bookings()
    time_bookings = [b for b in bookings if b[0] == time]
    
    occupied_cabins = len(time_bookings)
    
    if occupied_cabins == 0:
        return 2
    elif occupied_cabins == 1:
        occupied_gender = time_bookings[0][2]
        if occupied_gender == user['gender']:
            return 1
        else:
            return 0
    else:
        return 0

def get_main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🚿 Забронировать душ"), KeyboardButton("📋 Мои брони")],
        [KeyboardButton("📊 Все бронирования"), KeyboardButton("❌ Отменить бронь")]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not get_user(user_id):
        keyboard = [
            [InlineKeyboardButton("👨 Муж.", callback_data="gender_male")],
            [InlineKeyboardButton("👩 Жен.", callback_data="gender_female")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🚿 Добро пожаловать в систему бронирования душа!\n\n"
            "Для начала выберите ваш пол:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "🚿 Добро пожаловать обратно!\n"
            "Используйте меню ниже для управления бронированиями:",
            reply_markup=get_main_menu_keyboard()
        )

async def gender_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    gender = query.data.split('_')[1]
    name = f"{query.from_user.first_name} {query.from_user.last_name or ''}".strip()
    
    save_user(user_id, gender, name)
    
    await query.edit_message_text(
        f"✅ Отлично! Ваш пол: {'👨 Муж.' if gender == 'male' else '👩 Жен.'}\n\n"
        "Теперь вы можете забронить душ. Используйте меню ниже:"
    )
    await query.message.reply_text(
        "Выберите действие:",
        reply_markup=get_main_menu_keyboard()
    )

async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Если пользователь в процессе бронирования, обрабатываем как ввод времени
    if context.user_data.get('booking_step') == 'waiting_time':
        # Проверяем, является ли сообщение командой меню
        text = update.message.text
        if text in ["🚿 Забронировать душ", "📋 Мои брони", "📊 Все бронирования", "❌ Отменить бронь"]:
            # Если это команда меню, сбрасываем состояние и обрабатываем команду
            context.user_data.pop('booking_step', None)
            await handle_menu_command(update, context)
        else:
            # Если это не команда меню, обрабатываем как ввод времени
            await handle_time_input(update, context)
        return
    
    await handle_menu_command(update, context)

async def handle_menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команд из меню"""
    text = update.message.text
    
    if text == "🚿 Забронировать душ":
        await start_booking(update, context)
    elif text == "📋 Мои брони":
        await show_my_bookings(update, context)
    elif text == "📊 Все бронирования":
        await show_all_bookings(update, context)
    elif text == "❌ Отменить бронь":
        await cancel_booking_menu(update, context)

async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем старые брони перед показом
    cleanup_old_bookings()
    
    bookings = get_all_bookings()
    
    if bookings:
        time_groups = {}
        for time, cabin, gender, name in bookings:
            if time not in time_groups:
                time_groups[time] = []
            time_groups[time].append((cabin, gender, name))
        
        busy_text = "📊 Текущие бронирования:\n\n"
        
        for time, cabins in sorted(time_groups.items()):
            busy_text += f"🕐 {time}:\n"
            for cabin, gender, name in cabins:
                gender_icon = "👨" if gender == "male" else "👩"
                busy_text += f"   🚿 Ключ {cabin} {gender_icon} {name}\n"
            busy_text += "\n"
    else:
        busy_text = "📊 На данный момент нет бронирований."
    
    context.user_data['booking_step'] = 'waiting_time'
    
    await update.message.reply_text(
        f"{busy_text}\n\n"
        "⏰ Введите время для бронирования в формате ЧЧ:MM (например, 14:30):\n\n"
        "💡 Вы можете вернуться в меню, нажав любую кнопку ниже",
        reply_markup=get_main_menu_keyboard()
    )

async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    time_text = update.message.text.strip()
    
    try:
        datetime.strptime(time_text, "%H:%M")
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат времени. Пожалуйста, введите время в формате ЧЧ:MM (например, 14:30):"
        )
        return
    
    available_cabins = check_availability(time_text, user_id)
    
    if available_cabins == 0:
        current_bookings = [b for b in get_all_bookings() if b[0] == time_text]
        reason = "оба ключа заняты" if len(current_bookings) == 2 else "разные полы не могут делить время"
        
        await update.message.reply_text(
            f"❌ На время {time_text} нет свободных кабинок.\n"
            f"ℹ️ Причина: {reason}\n"
            "Пожалуйста, выберите другое время:"
        )
        return
    
    context.user_data['selected_time'] = time_text
    context.user_data['available_cabins'] = available_cabins
    context.user_data['booking_step'] = None
    
    keyboard = []
    
    if available_cabins >= 1:
        keyboard.append([InlineKeyboardButton("🚿 1 ключ", callback_data="confirm_1")])
    if available_cabins == 2:
        keyboard.append([InlineKeyboardButton("🚿🚿 2 ключа", callback_data="confirm_2")])
    
    keyboard.append([InlineKeyboardButton("🔙 Отмена", callback_data="cancel_booking_process")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"🕐 Время: {time_text}\n"
        f"📊 Доступно ключей: {available_cabins}\n\n"
        "Выберите количество ключей:",
        reply_markup=reply_markup
    )

async def confirm_booking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    cabins_count = int(query.data.split('_')[1])
    selected_time = context.user_data.get('selected_time')
    user_id = query.from_user.id
    
    if not selected_time:
        await query.edit_message_text("❌ Ошибка: время не выбрано. Начните бронирование заново.")
        return
    
    available_cabins = check_availability(selected_time, user_id)
    if available_cabins < cabins_count:
        await query.edit_message_text(
            f"❌ К сожалению, сейчас доступно только {available_cabins} ключ(ей) на время {selected_time}. "
            "Пожалуйста, начните бронирование заново."
        )
        context.user_data.pop('selected_time', None)
        context.user_data.pop('available_cabins', None)
        return
    
    available_cabins_list = [1, 2]
    existing_bookings = get_all_bookings()
    existing_cabins = [b[1] for b in existing_bookings if b[0] == selected_time]
    free_cabins = [c for c in available_cabins_list if c not in existing_cabins]
    
    booked_cabins = []
    for i in range(min(cabins_count, len(free_cabins))):
        create_booking(user_id, selected_time, free_cabins[i])
        booked_cabins.append(free_cabins[i])
    
    context.user_data.pop('selected_time', None)
    context.user_data.pop('available_cabins', None)
    
    if cabins_count == 1:
        cabins_text = f"ключ {booked_cabins[0]}"
    else:
        cabins_text = f"ключи {booked_cabins[0]} и {booked_cabins[1]}"
    
    # Показываем подтверждение брони
    await query.edit_message_text(
        f"✅ Бронирование подтверждено!\n\n"
        f"🕐 Время: {selected_time}\n"
        f"🚿 Забронировано: {cabins_text}\n\n"
    )
    
    # ПОСЛЕ КАЖДОЙ БРОНИ ПОКАЗЫВАЕМ ПОЛНЫЙ СПИСОК БРОНЕЙ
    await show_all_bookings_after_booking(query, context)

async def show_all_bookings_after_booking(query, context: ContextTypes.DEFAULT_TYPE):
    """Показывает полный список броней после добавления новой брони"""
    # Очищаем старые брони
    cleanup_old_bookings()
    
    bookings = get_all_bookings()
    
    if not bookings:
        await context.bot.send_message(chat_id=query.message.chat_id, 
                                     text="📊 На данный момент нет брони.")
        return
    
    time_groups = {}
    for time, cabin, gender, name in bookings:
        if time not in time_groups:
            time_groups[time] = []
        time_groups[time].append((cabin, gender, name))
    
    bookings_text = "📊 Все брони:\n\n"
    
    for time, cabins in sorted(time_groups.items()):
        bookings_text += f"⏰ {time}:\n"
        for cabin, gender, name in cabins:
            gender_icon = "👨" if gender == "male" else "👩"
            bookings_text += f"   🚿 Ключ {cabin} {gender_icon} {name}\n"
        bookings_text += "\n"
    
    await context.bot.send_message(chat_id=query.message.chat_id, 
                                 text=bookings_text,
                                 reply_markup=get_main_menu_keyboard())

async def show_my_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем старые брони перед показом
    cleanup_old_bookings()
    
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)
    
    if not bookings:
        await update.message.reply_text("📭 У вас нет активных броней.")
        return
    
    bookings_text = "📋 Ваши брони:\n\n"
    
    for booking in bookings:
        booking_id, time, cabin = booking
        bookings_text += f"⏰ {time} - 🚿 Ключ {cabin}\n"
    
    keyboard = [
        [InlineKeyboardButton("❌ Отменить бронь", callback_data="cancel_my_booking")],
        [InlineKeyboardButton("🔄 Обновить список", callback_data="refresh_my_bookings")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(bookings_text, reply_markup=reply_markup)

async def show_all_bookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очищаем старые брони перед показом
    cleanup_old_bookings()
    
    bookings = get_all_bookings()
    
    if not bookings:
        await update.message.reply_text("📊 На данный момент нет брони.")
        return
    
    time_groups = {}
    for time, cabin, gender, name in bookings:
        if time not in time_groups:
            time_groups[time] = []
        time_groups[time].append((cabin, gender, name))
    
    bookings_text = "📊 Все брони:\n\n"
    
    for time, cabins in sorted(time_groups.items()):
        bookings_text += f"⏰ {time}:\n"
        for cabin, gender, name in cabins:
            gender_icon = "👨" if gender == "male" else "👩"
            bookings_text += f"   🚿 Ключ {cabin} {gender_icon} {name}\n"
        bookings_text += "\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_all_bookings")],
        [InlineKeyboardButton("🚿 Забронировать", callback_data="book_from_list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(bookings_text, reply_markup=reply_markup)

async def cancel_booking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню отмены бронирования - показываем только свои брони"""
    # Очищаем старые брони перед показом
    cleanup_old_bookings()
    
    user_id = update.effective_user.id
    bookings = get_user_bookings(user_id)
    
    if not bookings:
        await update.message.reply_text("У вас нет активных бронирований для отмены.")
        return
    
    keyboard = []
    
    for booking in bookings:
        booking_id, time, cabin = booking
        button_text = f"⏰ {time} (ключ {cabin})"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cancel_{booking_id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите бронирование для отмены:",
        reply_markup=reply_markup
    )

async def handle_cancel_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отмены бронирования с проверкой владельца"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data.startswith('cancel_'):
        # Проверяем, это отмена конкретной брони (cancel_123) или меню отмены (cancel_my_booking)
        parts = query.data.split('_')
        if len(parts) == 2 and parts[1].isdigit():
            # Это отмена конкретной брони: cancel_123
            booking_id = int(parts[1])
            
            # ✅ Проверяем, принадлежит ли бронь этому пользователю
            booking_owner = get_booking_owner(booking_id)
            
            if booking_owner != user_id:
                await query.edit_message_text("❌ Ошибка: вы не можете отменить чужое бронирование!")
                return
            
            delete_booking(booking_id)
            await query.edit_message_text("✅ Бронирование успешно отменено!")
        elif query.data == "cancel_my_booking":
            # Это кнопка "Отменить бронь" из меню
            await cancel_booking_from_message(query.message, context)
        
    elif query.data == "refresh_my_bookings":
        await refresh_my_bookings(query.message, context)
    elif query.data == "refresh_all_bookings":
        await refresh_all_bookings(query.message, context)
    elif query.data == "book_from_list":
        await start_booking_from_message(query.message, context)
    elif query.data == "cancel_booking_process":
        await query.edit_message_text("❌ Процесс бронирования отменен.")
        context.user_data.pop('booking_step', None)
        context.user_data.pop('selected_time', None)
        context.user_data.pop('available_cabins', None)
    elif query.data == "back_to_menu":
        await query.edit_message_text("Возврат в главное меню")

async def cancel_booking_from_message(message, context):
    await cancel_booking_menu(Update(message=message), context)

async def refresh_my_bookings(message, context):
    await show_my_bookings(Update(message=message), context)

async def refresh_all_bookings(message, context):
    await show_all_bookings(Update(message=message), context)

async def start_booking_from_message(message, context):
    await start_booking(Update(message=message), context)

def main():
    init_db()
    
    application = Application.builder().token("8530588036:AAHXMSKnoRV8lApbLSY8WcCOmwJg3cSObEw").build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(gender_selection, pattern="^gender_"))
    application.add_handler(CallbackQueryHandler(confirm_booking, pattern="^confirm_"))
    application.add_handler(CallbackQueryHandler(handle_cancel_confirmation, pattern="^cancel_"))
    application.add_handler(CallbackQueryHandler(handle_cancel_confirmation, pattern="^refresh_"))
    application.add_handler(CallbackQueryHandler(handle_cancel_confirmation, pattern="^book_from_list"))
    application.add_handler(CallbackQueryHandler(handle_cancel_confirmation, pattern="^back_to_menu"))
    application.add_handler(CallbackQueryHandler(handle_cancel_confirmation, pattern="^cancel_booking_process"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_main_menu))
    
    application.run_polling()

if __name__ == '__main__':
    main()
