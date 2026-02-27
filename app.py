import requests
import os
from flask import Flask, request
import json

TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
app = Flask(__name__)

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
            url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
            data = {
                'chat_id': chat_id,
                'text': 'Бот работает! 🚀'
            }
            requests.post(url, data=data)
    
    return 'OK', 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)