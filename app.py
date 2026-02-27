import requests
import os
from flask import Flask, request
import json

TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
app = Flask(__name__)

def send_telegram_message(chat_id, text, buttons=None):
    url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if buttons:
        data['reply_markup'] = json.dumps({'inline_keyboard': buttons})
    requests.post(url, data=data)

@app.route('/')
def home():
    return 'Bot is running'

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.get_json()
    
    if 'message' in update:
        chat_id = update['message']['chat']['id']
        text = update['message'].get('text', '')
        
        if text == '/start':
            buttons = [
                [{'text': '📊 Статистика', 'callback_data': 'stats'}],
                [{'text': 'ℹ️ О боте', 'callback_data': 'about'}]
            ]
            send_telegram_message(chat_id, 'Выберите действие:', buttons)
    
    elif 'callback_query' in update:
        callback = update['callback_query']
        chat_id = callback['from']['id']
        data = callback['data']
        
        if data == 'stats':
            send_telegram_message(chat_id, '📊 Статистика пока пуста')
        elif data == 'about':
            send_telegram_message(chat_id, 'ℹ️ Бот для мониторинга отзывов')
        
        requests.post(f'https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery',
                     json={'callback_query_id': callback['id']})
    
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)