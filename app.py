import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask, request
import schedule
import threading
from datetime import datetime
import json

# =====================================
# ТВОИ ДАННЫЕ
# =====================================
TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
TG_ADMIN_ID = os.environ.get('TG_ADMIN_ID', '5434465388')  # Твой Telegram ID

SENT_REVIEWS_FILE = 'sent_reviews.txt'
STATS_FILE = 'review_stats.json'
LAST_REVIEWS_FILE = 'last_reviews.json'
CLIENTS_FILE = 'clients.json'  # Файл с клиентами

app = Flask(__name__)

# =====================================
# СЛОВАРИ ДЛЯ АНАЛИЗА ТОНАЛЬНОСТИ
# =====================================
NEGATIVE_WORDS = ['ужас', 'кошмар', 'проблем', 'не работа', 'плох', 'груб', 'хам', 'долг', 'очеред', 'не приш', 'обман', 'брак', 'сломан', 'гряз', 'холодн']
POSITIVE_WORDS = ['отличн', 'супер', 'спасиб', 'молодец', 'быстр', 'вежлив', 'чист', 'светл', 'уютн', 'классн', 'помог', 'совету', 'доволен']

# =====================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ФАЙЛАМИ
# =====================================
def load_clients():
    """Загружает список клиентов"""
    try:
        with open(CLIENTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Клиент по умолчанию (ты)
        default_clients = [
            {
                'id': 'client_1',
                'name': 'Мой ПВЗ (Ладо Кецховели)',
                'chat_id': TG_ADMIN_ID,
                'urls': {
                    '2gis': ['https://2gis.ru/krasnoyarsk/firm/70000001103415416/tab/reviews'],
                    'yandex': ['https://yandex.ru/maps/org/ozon/87014746999/reviews/']
                }
            },
            {
                'id': 'client_2',
                'name': 'Мой ПВЗ (Петра Ломако)',
                'chat_id': TG_ADMIN_ID,
                'urls': {
                    '2gis': ['https://2gis.ru/krasnoyarsk/firm/70000001101179865/tab/reviews'],
                    'yandex': ['https://yandex.ru/maps/org/ozon/80264119858/reviews/']
                }
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
# КЛАССЫ ДЛЯ ПАРСЕРОВ
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
# ОСНОВНАЯ ПРОВЕРКА НОВЫХ ОТЗЫВОВ ДЛЯ ВСЕХ КЛИЕНТОВ
# =====================================
def check_all_clients():
    """Проверяет отзывы для всех клиентов"""
    clients = load_clients()
    sent_reviews = load_sent_reviews()
    stats = load_stats()
    today = datetime.now().strftime('%Y-%m-%d')
    last_reviews = load_last_reviews()
    
    if stats['last_updated'] != today:
        stats['last_week_total'] = stats['total_reviews']
        stats['last_updated'] = today
    
    for client in clients:
        chat_id = client['chat_id']
        client_name = client['name']
        
        # 2ГИС
        for url in client['urls'].get('2gis', []):
            reviews = parse_reviews_from_2gis(url)
            for review in reviews:
                if review['id'] not in sent_reviews:
                    sentiment = analyze_sentiment(review['text'])
                    message = f'📝 <b>НОВЫЙ ОТЗЫВ</b> для {client_name}\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {review["url"]}'
                    send_telegram_message(chat_id, message)
                    save_sent_review(review['id'])
                    last_reviews.append(review)
                    stats['total_reviews'] += 1
                    stats['weekly_reviews'] += 1
                    time.sleep(1)
            time.sleep(2)
        
        # Яндекс
        yandex_parser = YandexMapsParser()
        for url in client['urls'].get('yandex', []):
            reviews = yandex_parser.fetch_reviews(url)
            for review in reviews:
                if review['id'] not in sent_reviews:
                    sentiment = analyze_sentiment(review['text'])
                    message = f'📝 <b>НОВЫЙ ОТЗЫВ (Яндекс)</b> для {client_name}\n\n👤 {review["name"]}\n{sentiment}\n📅 {review["date"]}\n\n💬 {review["text"][:200]}\n\n🔗 {url}'
                    send_telegram_message(chat_id, message)
                    save_sent_review(review['id'])
                    last_reviews.append(review)
                    stats['total_reviews'] += 1
                    stats['weekly_reviews'] += 1
                    time.sleep(1)
            time.sleep(2)
    
    save_stats(stats)
    save_last_reviews(last_reviews)

# =====================================
# ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА ДЛЯ ВСЕХ
# =====================================
def send_weekly_stats():
    stats = load_stats()
    weekly = stats.get('weekly_reviews', 0)
    total = stats.get('total_reviews', 0)
    last_week = stats.get('last_week_total', 0)
    clients = load_clients()
    
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
    
    for client in clients:
        message = f"""📊 <b>ЕЖЕНЕДЕЛЬНАЯ СТАТИСТИКА</b> для {client['name']}

📅 Неделя: {datetime.now().strftime('%d.%m.%Y')}

📝 Всего отзывов за неделю: {weekly}
📚 Всего отзывов за всё время: {total}

{trend}

Продолжаем мониторинг! 🚀"""
        
        send_telegram_message(client['chat_id'], message)
    
    stats['weekly_reviews'] = 0
    save_stats(stats)

# =====================================
# АДМИН-ПАНЕЛЬ В TELEGRAM
# =====================================
def show_admin_menu(chat_id):
    """Показывает админ-меню"""
    if str(chat_id) != TG_ADMIN_ID:
        send_telegram_message(chat_id, "⛔ У вас нет прав администратора")
        return
    
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

# =====================================
# WEBHOOK ДЛЯ TELEGRAM
# =====================================
@app.route('/webhook', methods=['POST'])
def webhook():
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
            
            # Если это админ, добавляем кнопку админки
            if str(chat_id) == TG_ADMIN_ID:
                buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
            
            message = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ ВАШЕГО БИЗНЕСА</b>

Бот отслеживает отзывы о ваших точках в 2ГИС и Яндекс Картах.

Выберите действие:"""
            
            send_telegram_message(chat_id, message, buttons)
            
    elif 'callback_query' in update:
        callback = update['callback_query']
        callback_data = callback['data']
        chat_id = callback['from']['id']
        
        # Админ-функции
        if callback_data == 'admin':
            show_admin_menu(chat_id)
            
        elif callback_data == 'admin_add':
            if str(chat_id) != TG_ADMIN_ID:
                send_telegram_message(chat_id, "⛔ Нет доступа")
            else:
                send_telegram_message(chat_id, "✏️ Введите данные клиента в формате:\n\n<code>Название\nСсылка на 2ГИС\nСсылка на Яндекс</code>\n\n(можно пропустить ссылку, поставив прочерк -)")
                # Здесь нужно будет добавить обработку ответа
                
        elif callback_data == 'admin_list':
            if str(chat_id) != TG_ADMIN_ID:
                send_telegram_message(chat_id, "⛔ Нет доступа")
            else:
                clients = load_clients()
                if not clients:
                    text = "📭 Клиентов пока нет"
                else:
                    text = "📋 <b>Список клиентов:</b>\n\n"
                    for i, client in enumerate(clients, 1):
                        text += f"{i}. {client['name']}\n   🆔 {client['id']}\n   💬 Chat ID: {client['chat_id']}\n\n"
                send_telegram_message(chat_id, text)
                
        elif callback_data == 'admin_delete':
            if str(chat_id) != TG_ADMIN_ID:
                send_telegram_message(chat_id, "⛔ Нет доступа")
            else:
                clients = load_clients()
                if not clients:
                    send_telegram_message(chat_id, "📭 Клиентов нет")
                else:
                    buttons = []
                    for client in clients:
                        buttons.append([{'text': f"❌ {client['name']}", 'callback_data': f"del_{client['id']}"}])
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
                show_admin_menu(chat_id)
                
        elif callback_data == 'main_menu':
            # Возврат в главное меню
            buttons = [
                [{'text': '📊 Статистика', 'callback_data': 'stats'},
                 {'text': '🔄 Проверить сейчас', 'callback_data': 'check'}],
                [{'text': '📋 Последние отзывы', 'callback_data': 'last'},
                 {'text': 'ℹ️ О боте', 'callback_data': 'about'}]
            ]
            if str(chat_id) == TG_ADMIN_ID:
                buttons.append([{'text': '👑 Админ-панель', 'callback_data': 'admin'}])
            
            message = """<b>🔍 МОНИТОРИНГ ОТЗЫВОВ ВАШЕГО БИЗНЕСА</b>

Бот отслеживает отзывы о ваших точках в 2ГИС и Яндекс Картах.

Выберите действие:"""
            
            send_telegram_message(chat_id, message, buttons)
            
        # Обычные функции
        elif callback_data == 'stats':
            stats = load_stats()
            text = f"""📊 <b>ТЕКУЩАЯ СТАТИСТИКА</b>

📝 За неделю: {stats.get('weekly_reviews', 0)}
📚 Всего: {stats.get('total_reviews', 0)}

📅 Последнее обновление: {stats.get('last_updated', 'никогда')}"""
            
        elif callback_data == 'check':
            send_telegram_message(chat_id, "🔄 Запускаю проверку...")
            check_all_clients()
            text = "✅ Проверка завершена"
            
        elif callback_data == 'last':
            last_reviews = load_last_reviews()
            if not last_reviews:
                text = "📭 Пока нет сохранённых отзывов"
            else:
                text = "📋 <b>Последние 5 отзывов:</b>\n\n"
                for i, r in enumerate(last_reviews[-5:], 1):
                    sentiment = analyze_sentiment(r['text'])
                    text += f"{i}. {r['name']} {sentiment}\n   {r['text'][:100]}...\n\n"
                    
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
        
        else:
            text = "Команда не распознана"
        
        if callback_data not in ['admin', 'admin_add', 'admin_list', 'admin_delete', 'main_menu']:
            send_telegram_message(chat_id, text)
        
        # Отвечаем на callback
        answer_url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/answerCallbackQuery'
        requests.post(answer_url, json={'callback_query_id': callback['id']})
    
    return 'OK'

# =====================================
# ОСНОВНЫЕ МАРШРУТЫ
# =====================================
@app.route('/')
def home():
    return 'Bot is running'

@app.route('/check')
def manual_check():
    check_all_clients()
    return 'Check completed'

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
    schedule.every().day.at('10:00').do(check_all_clients)
    schedule.every().sunday.at('20:00').do(send_weekly_stats)
    
    threading.Thread(target=run_schedule, daemon=True).start()
    
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)