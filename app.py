import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask
import schedule
import threading
from datetime import datetime, timedelta
import json

# =====================================
# ТВОИ ДАННЫЕ
# =====================================
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID', '5434465388')

PVZ_URLS = [
    'https://2gis.ru/krasnoyarsk/firm/70000001103415416/tab/reviews',
    'https://2gis.ru/krasnoyarsk/firm/70000001101179865/tab/reviews'
]

YANDEX_URLS = [
    'https://yandex.ru/maps/org/ozon/87014746999/reviews/',
    'https://yandex.ru/maps/org/ozon/80264119858/reviews/'
]

SENT_REVIEWS_FILE = 'sent_reviews.txt'
STATS_FILE = 'review_stats.json'
app = Flask(__name__)

# =====================================
# СЛОВАРИ ДЛЯ АНАЛИЗА ТОНАЛЬНОСТИ
# =====================================
NEGATIVE_WORDS = ['ужас', 'кошмар', 'проблем', 'не работа', 'плох', 'груб', 'хам', 'долг', 'очеред', 'не приш', 'обман', 'брак', 'сломан', 'гряз', 'холодн']
POSITIVE_WORDS = ['отличн', 'супер', 'спасиб', 'молодец', 'быстр', 'вежлив', 'чист', 'светл', 'уютн', 'классн', 'помог', 'совету', 'доволен']

# =====================================
# КЛАСС ДЛЯ ЯНДЕКС КАРТ
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
                review_id = f'ya_{name}_{date}_{text[:30]}'
                reviews.append({'id': review_id, 'name': name, 'text': text, 'date': date, 'source': 'yandex'})
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
# ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ
# =====================================
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

# =====================================
# АНАЛИЗ ТОНАЛЬНОСТИ
# =====================================
def analyze_sentiment(text):
    text_lower = text.lower()
    is_negative = any(word in text_lower for word in NEGATIVE_WORDS)
    is_positive = any(word in text_lower for word in POSITIVE_WORDS)
    
    if is_negative:
        return '🔴 НЕГАТИВНЫЙ'
    elif is_positive:
        return '🟢 ПОЗИТИВНЫЙ'
    else:
        return '⚪ НЕЙТРАЛЬНЫЙ'

# =====================================
# ОТПРАВКА В TELEGRAM
# =====================================
def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
    data = {'chat_id': TG_CHAT_ID, 'text': text}
    response = requests.post(url, data=data)
    return response.status_code == 200

# =====================================
# ПАРСИНГ 2ГИС
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
            review_id = f'{name}_{date}_{text[:30]}'
            reviews.append({'id': review_id, 'name': name, 'text': text, 'date': date, 'url': url})
        except:
            continue
    return reviews

# =====================================
# ОСНОВНАЯ ПРОВЕРКА НОВЫХ ОТЗЫВОВ
# =====================================
def check_new_reviews():
    sent_reviews = load_sent_reviews()
    new_found = False
    stats = load_stats()
    today = datetime.now().strftime('%Y-%m-%d')
    
    if stats['last_updated'] != today:
        stats['last_week_total'] = stats['total_reviews']
        stats['last_updated'] = today
    
    new_reviews_list = []
    
    # Парсинг 2ГИС
    for url in PVZ_URLS:
        reviews = parse_reviews_from_2gis(url)
        for review in reviews:
            if review['id'] not in sent_reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 НОВЫЙ ОТЗЫВ\n{send_telegram_message}\n👤 {review["name"]}\n📅 {review["date"]}\n{send_telegram_message}\n💬 {review["text"][:200]}\n{send_telegram_message}\n🔗 {review["url"]}'
                send_telegram_message(message)
                save_sent_review(review['id'])
                new_found = True
                new_reviews_list.append(review)
                stats['total_reviews'] += 1
                stats['weekly_reviews'] += 1
                time.sleep(1)
        time.sleep(2)
    
    # Парсинг Яндекс Карт
    yandex_parser = YandexMapsParser()
    for url in YANDEX_URLS:
        reviews = yandex_parser.fetch_reviews(url)
        for review in reviews:
            if review['id'] not in sent_reviews:
                sentiment = analyze_sentiment(review['text'])
                message = f'📝 НОВЫЙ ОТЗЫВ (Яндекс)\n{send_telegram_message}\n👤 {review["name"]}\n{send_telegram_message}{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {url}'
                send_telegram_message(message)
                save_sent_review(review['id'])
                new_found = True
                new_reviews_list.append(review)
                stats['total_reviews'] += 1
                stats['weekly_reviews'] += 1
                time.sleep(1)
        time.sleep(2)
    
    save_stats(stats)
    return new_found

# =====================================
# ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА
# =====================================
def send_weekly_stats():
    stats = load_stats()
    weekly = stats.get('weekly_reviews', 0)
    total = stats.get('total_reviews', 0)
    last_week = stats.get('last_week_total', 0)
    
    # Динамика
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
    
    message = f"""📊 ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА

📅 Неделя: {datetime.now().strftime('%d.%m.%Y')}

📝 Всего отзывов за неделю: {weekly}
📚 Всего отзывов за всё время: {total}

{trend}

Продолжаем мониторинг! 🚀"""
    
    send_telegram_message(message)
    
    # Обнуляем недельную статистику
    stats['weekly_reviews'] = 0
    save_stats(stats)

# =====================================
# FLASK-МАРШРУТЫ
# =====================================
@app.route('/')
def home():
    return 'Bot is running'

@app.route('/check')
def manual_check():
    result = check_new_reviews()
    return f'Check completed. New reviews: {result}'

@app.route('/stats')
def manual_stats():
    send_weekly_stats()
    return 'Weekly stats sent'

# =====================================
# ПЛАНИРОВЩИК
# =====================================
def run_schedule():
    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == '__main__':
    # Ежедневная проверка в 10:00
    schedule.every().day.at('10:00').do(check_new_reviews)
    
    # Еженедельная статистика каждое воскресенье в 20:00
    schedule.every().sunday.at('20:00').do(send_weekly_stats)
    
    threading.Thread(target=run_schedule, daemon=True).start()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)