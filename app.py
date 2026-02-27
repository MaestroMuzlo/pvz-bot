import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask, request
import schedule
import threading
from datetime import datetime, timedelta
import json
import psycopg2
from psycopg2.extras import RealDictCursor
import uuid

# =====================================
# ТВОИ ДАННЫЕ
# =====================================
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
TG_ADMIN_ID = os.environ.get('TG_ADMIN_ID', '5434465388')
DATABASE_URL = os.environ.get('DATABASE_URL')

app = Flask(__name__)

# =====================================
# ПОДКЛЮЧЕНИЕ К БАЗЕ ДАННЫХ
# =====================================
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            trial_until TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pvz (
            id TEXT PRIMARY KEY,
            client_id TEXT REFERENCES clients(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            url_2gis TEXT,
            url_yandex TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            pvz_id TEXT REFERENCES pvz(id) ON DELETE CASCADE,
            author_name TEXT,
            text TEXT,
            rating INTEGER,
            date TIMESTAMP,
            sentiment TEXT,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS subscriptions (
            id TEXT PRIMARY KEY,
            client_id TEXT REFERENCES clients(id) ON DELETE CASCADE,
            start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_date TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            payment_amount INTEGER,
            payment_method TEXT
        )
    ''')
    
    conn.commit()
    cur.close()
    conn.close()
    print("✅ База данных инициализирована")

# =====================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КЛИЕНТАМИ
# =====================================
def add_client(chat_id, name, trial_days=7):
    client_id = str(uuid.uuid4())[:8]
    trial_until = datetime.now() + timedelta(days=trial_days)
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO clients (id, name, chat_id, trial_until) VALUES (%s, %s, %s, %s)",
        (client_id, name, chat_id, trial_until)
    )
    conn.commit()
    cur.close()
    conn.close()
    return client_id

def get_client_by_chat_id(chat_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE chat_id = %s", (chat_id,))
    client = cur.fetchone()
    cur.close()
    conn.close()
    return client

def get_all_clients():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM clients WHERE is_active = TRUE")
    clients = cur.fetchall()
    cur.close()
    conn.close()
    return clients

def check_subscription(chat_id):
    client = get_client_by_chat_id(chat_id)
    if not client:
        return False
    if not client['trial_until']:
        return True
    return client['trial_until'] > datetime.now()

def get_all_pvz():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT p.*, c.chat_id, c.name as client_name 
        FROM pvz p 
        JOIN clients c ON p.client_id = c.id 
        WHERE c.is_active = TRUE
    """)
    pvz_list = cur.fetchall()
    cur.close()
    conn.close()
    return pvz_list

def get_last_reviews(limit=10):
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT r.*, p.name as pvz_name, c.name as client_name 
        FROM reviews r 
        JOIN pvz p ON r.pvz_id = p.id 
        JOIN clients c ON p.client_id = c.id 
        ORDER BY r.created_at DESC LIMIT %s
    """, (limit,))
    reviews = cur.fetchall()
    cur.close()
    conn.close()
    return reviews

def get_stats():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM reviews")
    total = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM reviews WHERE created_at > NOW() - INTERVAL '7 days'")
    weekly = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM clients")
    clients_count = cur.fetchone()[0]
    
    cur.execute("SELECT COUNT(*) FROM pvz")
    pvz_count = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return {
        'total_reviews': total,
        'weekly_reviews': weekly,
        'clients_count': clients_count,
        'pvz_count': pvz_count
    }

# =====================================
# АНАЛИЗ ТОНАЛЬНОСТИ
# =====================================
NEGATIVE_WORDS = ['ужас', 'кошмар', 'проблем', 'не работа', 'плох', 'груб', 'хам', 'долг', 'очеред', 'не приш', 'обман', 'брак', 'сломан', 'гряз', 'холодн']
POSITIVE_WORDS = ['отличн', 'супер', 'спасиб', 'молодец', 'быстр', 'вежлив', 'чист', 'светл', 'уютн', 'классн', 'помог', 'совету', 'доволен']

def analyze_sentiment(text):
    text_lower = text.lower()
    is_negative = any(word in text_lower for word in NEGATIVE_WORDS)
    is_positive = any(word in text_lower for word in POSITIVE_WORDS)
    
    if is_negative:
        return 'negative'
    elif is_positive:
        return 'positive'
    else:
        return 'neutral'

# =====================================
# ПАРСЕРЫ
# =====================================
class YandexMapsParser:
    def parse_reviews_from_html(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        reviews = []
        review_blocks = soup.find_all('div', class_='business-reviews-card-view__review')
        if not review_blocks:
            review_blocks = soup.find_all('div', class_='business-review-view')
        for block in review_blocks:
            try:
                name_elem = block.find('div', class_='business-review-view__author-name')
                if not name_elem:
                    name_elem = block.find('a', class_='business-review-view__link')
                name = name_elem.text.strip() if name_elem else 'Аноним'
                text_elem = block.find('div', class_='business-review-view__body')
                text = text_elem.text.strip() if text_elem else ''
                date_elem = block.find('span', class_='business-review-view__date')
                date = date_elem.text.strip() if date_elem else ''
                reviews.append({'name': name, 'text': text, 'date': date, 'source': 'yandex'})
            except:
                continue
        return reviews
    
    def fetch_reviews(self, url):
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return self.parse_reviews_from_html(response.text)
        return []

def parse_reviews_from_2gis(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    reviews = []
    review_blocks = soup.find_all('div', class_='_1k5soqfl')
    for block in review_blocks:
        try:
            name_elem = block.find('span', class_='_16s5yj36')
            name = name_elem.text if name_elem else 'Аноним'
            text_elem = block.find('a', class_='_1msln3t') or block.find('a', class_='_1wlx08h')
            text = text_elem.text if text_elem else ''
            date_elem = block.find('div', class_='_1evjsdb')
            date = date_elem.text if date_elem else ''
            reviews.append({'name': name, 'text': text, 'date': date, 'source': '2gis', 'url': url})
        except:
            continue
    return reviews

# =====================================
# ОТПРАВКА В TELEGRAM
# =====================================
def send_telegram_message(chat_id, text, buttons=None):
    url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    
    if buttons:
        data['reply_markup'] = json.dumps({'inline_keyboard': buttons})
    
    response = requests.post(url, data=data)
    return response.status_code == 200

# =====================================
# ОСНОВНАЯ ПРОВЕРКА НОВЫХ ОТЗЫВОВ
# =====================================
def check_all_reviews():
    all_pvz = get_all_pvz()
    yandex_parser = YandexMapsParser()
    
    for pvz in all_pvz:
        chat_id = pvz['chat_id']
        
        if not check_subscription(chat_id):
            continue
        
        if pvz['url_2gis']:
            reviews = parse_reviews_from_2gis(pvz['url_2gis'])
            for review in reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 <b>НОВЫЙ ОТЗЫВ</b> для {pvz["client_name"]} - {pvz["name"]}\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {pvz["url_2gis"]}'
                send_telegram_message(chat_id, message)
                time.sleep(1)
        
        if pvz['url_yandex']:
            reviews = yandex_parser.fetch_reviews(pvz['url_yandex'])
            for review in reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 <b>НОВЫЙ ОТЗЫВ (Яндекс)</b> для {pvz["client_name"]} - {pvz["name"]}\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {pvz["url_yandex"]}'
                send_telegram_message(chat_id, message)
                time.sleep(1)
        
        time.sleep(2)

# =====================================
# ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА
# =====================================
def send_weekly_stats():
    clients = get_all_clients()
    stats = get_stats()
    
    for client in clients:
        if not check_subscription(client['chat_id']):
            continue
            
        message = f"""📊 <b>ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА</b>

📅 Неделя: {datetime.now().strftime('%d.%m.%Y')}

📝 Всего отзывов за неделю: {stats['weekly_reviews']}
📚 Всего отзывов за всё время: {stats['total_reviews']}

Продолжаем мониторинг! 🚀"""
        
        send_telegram_message(client['chat_id'], message)

# =====================================
# WEBHOOK (ГЛАВНОЕ)
# =====================================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            if text == '/start':
                client = get_client_by_chat_id(chat_id)
                
                if client:
                    buttons = [
                        [{'text': '📊 Статистика', 'callback_data': 'stats'},
                         {'text': '🔄 Проверить сейчас', 'callback_data': 'check'}],
                        [{'text': '📋 Мои отзывы', 'callback_data': 'my_reviews'},
                         {'text': 'ℹ️ О боте', 'callback_data': 'about'}]
                    ]
                    
                    if str(chat_id) == TG_ADMIN_ID:
                        buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
                    
                    message = f"""<b>🔍 МОНИТОРИНГ ОТЗЫВОВ</b>

Добро пожаловать, {client['name']}!"""
                    
                else:
                    buttons = [
                        [{'text': '✅ Бесплатный тест на 7 дней', 'callback_data': 'trial'}],
                        [{'text': 'ℹ️ О боте', 'callback_data': 'about'}]
                    ]
                    message = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ ВАШЕГО БИЗНЕСА</b>

Бот отслеживает отзывы о ваших точках в 2ГИС и Яндекс Картах.

🔹 Бесплатный тест-драйв на 7 дней
🔹 Мгновенные уведомления
🔹 Анализ тональности
🔹 Еженедельная статистика"""
                
                send_telegram_message(chat_id, message, buttons)
                
        elif 'callback_query' in update:
            callback = update['callback_query']
            callback_data = callback['data']
            chat_id = callback['from']['id']
            
            if callback_data == 'admin':
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    stats = get_stats()
                    buttons = [
                        [{'text': '📊 Общая статистика', 'callback_data': 'admin_stats'}],
                        [{'text': '📋 Список клиентов', 'callback_data': 'admin_list'}],
                        [{'text': '➕ Добавить клиента', 'callback_data': 'admin_add'}],
                        [{'text': '🔙 Главное меню', 'callback_data': 'main_menu'}]
                    ]
                    message = f"""<b>👑 АДМИН-ПАНЕЛЬ</b>

📊 Статистика:
• Клиентов: {stats['clients_count']}
• ПВЗ: {stats['pvz_count']}
• Отзывов: {stats['total_reviews']}
• За неделю: {stats['weekly_reviews']}"""
                    send_telegram_message(chat_id, message, buttons)
                    
            elif callback_data == 'admin_stats':
                stats = get_stats()
                text = f"""📊 <b>ПОЛНАЯ СТАТИСТИКА</b>

👥 Клиентов: {stats['clients_count']}
📍 ПВЗ: {stats['pvz_count']}
📝 Всего отзывов: {stats['total_reviews']}
📅 За неделю: {stats['weekly_reviews']}"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'admin_list':
                clients = get_all_clients()
                if not clients:
                    text = "📭 Клиентов пока нет"
                else:
                    text = "📋 <b>Список клиентов:</b>\n\n"
                    for c in clients:
                        text += f"• {c['name']} (ID: {c['id']})\n  До: {c['trial_until']}\n\n"
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'trial':
                name = f"Клиент {chat_id}"
                client_id = add_client(chat_id, name)
                text = """✅ <b>Пробный период активирован!</b>

7 дней бесплатного мониторинга.

Теперь добавьте ваши ПВЗ, отправив ссылки в формате:
<code>Название ПВЗ
https://2gis.ru/...
https://yandex.ru/maps/...</code>"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'main_menu':
                client = get_client_by_chat_id(chat_id)
                buttons = [
                    [{'text': '📊 Статистика', 'callback_data': 'stats'},
                     {'text': '🔄 Проверить сейчас', 'callback_data': 'check'}],
                    [{'text': '📋 Мои отзывы', 'callback_data': 'my_reviews'},
                     {'text': 'ℹ️ О боте', 'callback_data': 'about'}]
                ]
                if str(chat_id) == TG_ADMIN_ID:
                    buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
                send_telegram_message(chat_id, "Главное меню", buttons)
                
            elif callback_data == 'about':
                text = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ</b>

<b>Что делает бот:</b>
• 📍 Отслеживает отзывы в 2ГИС и Яндекс Картах
• ⚡ Мгновенные уведомления
• 🎯 Анализ тональности
• 📊 Еженедельная статистика

<b>Тарифы:</b>
• 7 дней бесплатно
• Далее 500₽/мес

<b>🚀 Подключить бизнес:</b>
👉 @MaestroMuzlo"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'stats':
                stats = get_stats()
                text = f"""📊 <b>СТАТИСТИКА</b>

📝 За неделю: {stats['weekly_reviews']}
📚 Всего: {stats['total_reviews']}"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'check':
                send_telegram_message(chat_id, "🔄 Запускаю проверку...")
                check_all_reviews()
                send_telegram_message(chat_id, "✅ Проверка завершена")
                
            elif callback_data == 'my_reviews':
                last_reviews = get_last_reviews(5)
                if not last_reviews:
                    text = "📭 Пока нет отзывов"
                else:
                    text = "📋 <b>Последние 5 отзывов:</b>\n\n"
                    for r in last_reviews:
                        sentiment_emoji = '🔴' if r['sentiment'] == 'negative' else '🟢' if r['sentiment'] == 'positive' else '⚪'
                        text += f"{sentiment_emoji} {r['author_name']}\n   {r['text'][:100]}...\n\n"
                send_telegram_message(chat_id, text)
            
            answer_url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery'
            requests.post(answer_url, json={'callback_query_id': callback['id']})
    
    except Exception as e:
        print(f"Ошибка в webhook: {e}")
    
    return 'OK', 200

# =====================================
# ОСНОВНЫЕ МАРШРУТЫ
# =====================================
@app.route('/')
def home():
    return 'Bot is running', 200

@app.route('/check')
def manual_check():
    check_all_reviews()
    return 'Check completed', 200

@app.route('/stats')
def manual_stats():
    send_weekly_stats()
    return 'Stats sent', 200

@app.route('/test')
def test():
    return 'Test OK', 200

# =====================================
# ПЛАНИРОВЩИК
# =====================================
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    init_db()
    
    admin = get_client_by_chat_id(TG_ADMIN_ID)
    if not admin:
        add_client(TG_ADMIN_ID, 'Администратор', trial_days=999)
        print("✅ Администратор добавлен")
    
    schedule.every().day.at('10:00').do(check_all_reviews)
    schedule.every().sunday.at('20:00').do(send_weekly_stats)
    
    threading.Thread(target=run_schedule, daemon=True).start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)