import requests
import os
from flask import Flask, request
import json
import time
from bs4 import BeautifulSoup
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import uuid

TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
DATABASE_URL = os.environ.get('DATABASE_URL')
app = Flask(__name__)

def get_db():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pvz (
            id TEXT PRIMARY KEY,
            client_id TEXT REFERENCES clients(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            url_2gis TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            pvz_id TEXT REFERENCES pvz(id) ON DELETE CASCADE,
            author_name TEXT,
            text TEXT,
            date TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    cur.close()
    conn.close()
    print("✅ База данных готова")

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

def parse_2gis():
    url = 'https://2gis.ru/krasnoyarsk/firm/70000001103415416/tab/reviews'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    reviews = soup.find_all('div', class_='_1k5soqfl')
    return len(reviews)

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
                [{'text': '📊 Статистика', 'callback_data': 'stats'},
                 {'text': '🔄 Проверить', 'callback_data': 'check'}],
                [{'text': 'ℹ️ О боте', 'callback_data': 'about'}]
            ]
            send_telegram_message(chat_id, 'Выберите действие:', buttons)
    
    elif 'callback_query' in update:
        callback = update['callback_query']
        chat_id = callback['from']['id']
        data = callback['data']
        
        if data == 'stats':
            count = parse_2gis()
            send_telegram_message(chat_id, f'📊 Найдено отзывов: {count}')
        elif data == 'check':
            send_telegram_message(chat_id, '🔄 Проверка...')
            count = parse_2gis()
            send_telegram_message(chat_id, f'✅ Проверено. Отзывов: {count}')
        elif data == 'about':
            send_telegram_message(chat_id, 'ℹ️ Бот для мониторинга отзывов')
        
        requests.post(f'https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery',
                     json={'callback_query_id': callback['id']})
    
    return 'OK', 200

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)