from flask import Flask, request, jsonify
import os
from bot import setup_bot, application
import asyncio

app = Flask(__name__)

# Инициализация бота при старте
bot_app = setup_bot()

@app.route('/api/webhook', methods=['POST'])
def webhook():
    """Обработка webhook от Telegram"""
    try:
        # Получаем обновление от Telegram
        update_data = request.get_json()
        
        # Создаем объект Update
        update = Update.de_json(update_data, bot_app.bot)
        
        # Обрабатываем обновление асинхронно
        async def process_update():
            await bot_app.process_update(update)
        
        # Запускаем асинхронную обработку
        asyncio.run(process_update())
        
        return jsonify({"status": "ok"}), 200
        
    except Exception as e:
        print(f"Error processing update: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running", 
        "service": "Telegram Shower Booking Bot"
    })

@app.route('/api/set-webhook', methods=['GET'])
def set_webhook():
    """Установка webhook (вызвать один раз после деплоя)"""
    try:
        webhook_url = f"https://{request.host}/api/webhook"
        
        async def set_wh():
            await bot_app.bot.set_webhook(webhook_url)
        
        asyncio.run(set_wh())
        
        return jsonify({
            "status": "webhook set", 
            "url": webhook_url
        }), 200
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)