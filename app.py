import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask, request
import schedule
import threading
from datetime import datetime
import json
import uuid

# =====================================
# ТВОИ ДАННЫЕ
# =====================================
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
TG_ADMIN_ID = os.environ.get('TG_ADMIN_ID', '5434465388')

# =====================================
# ФАЙЛЫ ДЛЯ ХРАНЕНИЯ ДАННЫХ
# =====================================
SENT_REVIEWS_FILE = 'sent_reviews.txt'
STATS_FILE = 'review_stats.json'
LAST_REVIEWS_FILE = 'last_reviews.json'
CLIENTS_FILE = 'clients.json'

app = Flask(__name__)

# =====================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ
# =====================================
def load_clients():
    try:
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        default_clients = [
            {
                'id': 'admin',
                'name': 'Администратор',
                'chat_id': TG_ADMIN_ID,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]
        save_clients(default_clients)
        return default_clients

def save_clients(clients):
    with open(CLIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(clients, f, ensure_ascii=False, indent=2)

def load_sent_reviews():
    try:
        with open(SENT_REVIEWS_FILE, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_sent_review(review_id):
    with open(SENT_REVIEWS_FILE, 'a', encoding='utf-8') as f:
        f.write(review_id + '\n')

def load_stats():
    try:
        with open(STATS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'total_reviews': 0, 'weekly_reviews': 0, 'last_week_total': 0, 'last_updated': None}

def save_stats(stats):
    with open(STATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

def load_last_reviews():
    try:
        with open(LAST_REVIEWS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_last_reviews(reviews):
    if len(reviews) > 10:
        reviews = reviews[-10:]
    with open(LAST_REVIEWS_FILE, 'w', encoding='utf-8') as f:
        json.dump(reviews, f, ensure_ascii=False, indent=2)

# =====================================
# СЛОВАРИ ДЛЯ АНАЛИЗА ТОНАЛЬНОСТИ
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
# ПАРСЕР 2ГИС
# =====================================
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
            reviews.append({'name': name, 'text': text, 'date': date, 'url': url})
        except:
            continue
    return reviews

# =====================================
# ПАРСЕР ЯНДЕКС КАРТ
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
    
    requests.post(url, data=data)

# =====================================
# ОСНОВНАЯ ПРОВЕРКА НОВЫХ ОТЗЫВОВ
# =====================================
def check_new_reviews():
    sent_reviews = load_sent_reviews()
    new_found = False
    stats = load_stats()
    today = datetime.now().strftime('%Y-%m-%d')
    last_reviews = load_last_reviews()
    
    if stats['last_updated'] != today:
        stats['last_week_total'] = stats['total_reviews']
        stats['last_updated'] = today
    
    PVZ_URLS = [
        'https://2gis.ru/krasnoyarsk/firm/70000001103415416/tab/reviews',
        'https://2gis.ru/krasnoyarsk/firm/70000001101179865/tab/reviews'
    ]
    
    YANDEX_URLS = [
        'https://yandex.ru/maps/org/ozon/87014746999/reviews/',
        'https://yandex.ru/maps/org/ozon/80264119858/reviews/'
    ]
    
    for url in PVZ_URLS:
        reviews = parse_reviews_from_2gis(url)
        for review in reviews:
            review_id = f"{review['name']}_{review['date']}_{review['text'][:30]}"
            if review_id not in sent_reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 <b>НОВЫЙ ОТЗЫВ</b>\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {url}'
                send_telegram_message(TG_ADMIN_ID, message)
                save_sent_review(review_id)
                last_reviews.append(review)
                new_found = True
                stats['total_reviews'] += 1
                stats['weekly_reviews'] += 1
                time.sleep(1)
        time.sleep(2)
    
    yandex_parser = YandexMapsParser()
    for url in YANDEX_URLS:
        reviews = yandex_parser.fetch_reviews(url)
        for review in reviews:
            review_id = f"{review['name']}_{review['date']}_{review['text'][:30]}"
            if review_id not in sent_reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 <b>НОВЫЙ ОТЗЫВ (Яндекс)</b>\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {url}'
                send_telegram_message(TG_ADMIN_ID, message)
                save_sent_review(review_id)
                last_reviews.append(review)
                new_found = True
                stats['total_reviews'] += 1
                stats['weekly_reviews'] += 1
                time.sleep(1)
        time.sleep(2)
    
    save_stats(stats)
    save_last_reviews(last_reviews)
    return new_found

# =====================================
# ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА
# =====================================
def send_weekly_stats():
    stats = load_stats()
    weekly = stats.get('weekly_reviews', 0)
    total = stats.get('total_reviews', 0)
    last_week = stats.get('last_week_total', 0)
    
    if last_week > 0:
        change = weekly - last_week
        if change > 0:
            trend = f'📈 +{change} (больше чем на прошлой неделе)'
        elif change < 0:
            trend = f'📉 {change} (меньше чем на прошлой неделе)'
        else:
            trend = '➖ Столько же, как на прошлой неделе'
    else:
        trend = '📊 Это первая неделя мониторинга'
    
    message = f"""📊 <b>ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА</b>

📅 Неделя: {datetime.now().strftime('%d.%m.%Y')}

📝 Всего отзывов за неделю: {weekly}
📚 Всего отзывов за всё время: {total}

{trend}

Продолжаем мониторинг! 🚀"""
    
    send_telegram_message(TG_ADMIN_ID, message)
    
    stats['weekly_reviews'] = 0
    save_stats(stats)

# =====================================
# WEBHOOK
# =====================================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        update = request.get_json()
        
        if 'message' in update:
            chat_id = update['message']['chat']['id']
            text = update['message'].get('text', '')
            
            if text == '/start':
                buttons = [
                    [{'text': '📊 Статистика', 'callback_data': 'stats'},
                     {'text': '🔄 Проверить сейчас', 'callback_data': 'check'}],
                    [{'text': '📋 Последние отзывы', 'callback_data': 'last'},
                     {'text': 'ℹ️ О боте', 'callback_data': 'about'}]
                ]
                
                if str(chat_id) == TG_ADMIN_ID:
                    buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
                
                message = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ</b>

Бот отслеживает отзывы о ваших точках в 2ГИС и Яндекс Картах.

Выберите действие:"""
                
                send_telegram_message(chat_id, message, buttons)
                
        elif 'callback_query' in update:
            callback = update['callback_query']
            callback_data = callback['data']
            chat_id = callback['from']['id']
            
            if callback_data == 'admin':
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    buttons = [
                        [{'text': '➕ Добавить клиента', 'callback_data': 'admin_add'}],
                        [{'text': '📋 Список клиентов', 'callback_data': 'admin_list'}],
                        [{'text': '🗑️ Удалить клиента', 'callback_data': 'admin_delete'}],
                        [{'text': '🔙 Главное меню', 'callback_data': 'main_menu'}]
                    ]
                    message = """<b>👑 АДМИН-ПАНЕЛЬ</b>

Управление клиентами бота:

➕ Добавить нового клиента
📋 Посмотреть всех подключённых
🗑️ Удалить клиента"""
                    send_telegram_message(chat_id, message, buttons)
                    
            elif callback_data == 'admin_add':
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    send_telegram_message(chat_id, "✏️ Функция добавления клиента будет позже")
                    
            elif callback_data == 'admin_list':
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    clients = load_clients()
                    if not clients:
                        text = "📭 Клиентов пока нет"
                    else:
                        text = "📋 <b>Список клиентов:</b>\n\n"
                        for c in clients:
                            text += f"• {c['name']} (ID: {c['id']})\n  Chat: {c['chat_id']}\n\n"
                    send_telegram_message(chat_id, text)
                    
            elif callback_data == 'admin_delete':
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    clients = load_clients()
                    if len(clients) <= 1:
                        send_telegram_message(chat_id, "❌ Нельзя удалить последнего клиента")
                    else:
                        buttons = []
                        for c in clients[1:]:  # пропускаем админа
                            buttons.append([{'text': f"❌ {c['name']}", 'callback_data': f"del_{c['id']}"}])
                        buttons.append([{'text': '🔙 Назад', 'callback_data': 'admin'}])
                        send_telegram_message(chat_id, "🗑️ Выберите клиента для удаления:", buttons)
                        
            elif callback_data.startswith('del_'):
                if str(chat_id) != TG_ADMIN_ID:
                    send_telegram_message(chat_id, "⛔ Нет доступа")
                else:
                    client_id = callback_data[4:]
                    clients = load_clients()
                    clients = [c for c in clients if c['id'] != client_id]
                    save_clients(clients)
                    send_telegram_message(chat_id, f"✅ Клиент удалён")
                    
            elif callback_data == 'main_menu':
                buttons = [
                    [{'text': '📊 Статистика', 'callback_data': 'stats'},
                     {'text': '🔄 Проверить сейчас', 'callback_data': 'check'}],
                    [{'text': '📋 Последние отзывы', 'callback_data': 'last'},
                     {'text': 'ℹ️ О боте', 'callback_data': 'about'}]
                ]
                if str(chat_id) == TG_ADMIN_ID:
                    buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
                send_telegram_message(chat_id, "Главное меню", buttons)
                
            elif callback_data == 'about':
                text = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ ВАШЕГО БИЗНЕСА</b>

<b>Что делает бот:</b>
• 📍 Отслеживает отзывы о ваших точках в <b>2ГИС</b> и <b>Яндекс Картах</b>
• ⚡ Мгновенно присылает уведомления о новых отзывах
• 🎯 Анализирует тональность (негатив/позитив)
• 📊 Еженедельная статистика в Telegram

<b>Для кого:</b>
Владельцы ПВЗ, кафе, магазинов, салонов красоты, автомастерских — любого бизнеса с точками на карте.

<b>Преимущества:</b>
✅ Не пропустите ни одного негативного отзыва
✅ Оперативная реакция на проблемы клиентов
✅ Полный контроль репутации 24/7
✅ Работает в облаке — не нужен ваш компьютер

<b>🚀 Готовы подключить ваш бизнес?</b>
👉 @MaestroMuzlo"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'stats':
                stats = load_stats()
                text = f"""📊 <b>СТАТИСТИКА</b>

📝 За неделю: {stats['weekly_reviews']}
📚 Всего: {stats['total_reviews']}"""
                send_telegram_message(chat_id, text)
                
            elif callback_data == 'check':
                send_telegram_message(chat_id, "🔄 Запускаю проверку...")
                result = check_new_reviews()
                send_telegram_message(chat_id, f"✅ Проверка завершена. Новых отзывов: {result}")
                
            elif callback_data == 'last':
                last_reviews = load_last_reviews()
                if not last_reviews:
                    text = "📭 Пока нет отзывов"
                else:
                    text = "📋 <b>Последние 5 отзывов:</b>\n\n"
                    for i, r in enumerate(last_reviews[-5:], 1):
                        sentiment = analyze_sentiment(r['text'])
                        sentiment_emoji = '🔴' if sentiment == 'negative' else '🟢' if sentiment == 'positive' else '⚪'
                        text += f"{i}. {r['name']} {sentiment_emoji}\n   {r['text'][:100]}...\n\n"
                send_telegram_message(chat_id, text)
            
            answer_url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery'
            requests.post(answer_url, json={'callback_query_id': callback['id']})
    
    except Exception as e:
        print(f"Ошибка: {e}")
    
    return 'OK', 200

# =====================================
# ОСНОВНЫЕ МАРШРУТЫ
# =====================================
@app.route('/')
def home():
    return 'Bot is running', 200

@app.route('/check')
def manual_check():
    result = check_new_reviews()
    return f'Check completed. New reviews: {result}', 200

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
    schedule.every().day.at('10:00').do(check_new_reviews)
    schedule.every().sunday.at('20:00').do(send_weekly_stats)
    
    threading.Thread(target=run_schedule, daemon=True).start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)