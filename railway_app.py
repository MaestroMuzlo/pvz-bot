import requests
from bs4 import BeautifulSoup
import time
import os
from flask import Flask

TG_BOT_TOKEN = os.environ.get('TG_BOT_TOKEN', '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ')
TG_CHAT_ID = os.environ.get('TG_CHAT_ID', '5434465388')

PVZ_URLS = [
    'https://2gis.ru/krasnoyarsk/firm/70000001103415416/tab/reviews',
    'https://2gis.ru/krasnoyarsk/firm/70000001101179865/tab/reviews'
]

SENT_REVIEWS_FILE = 'sent_reviews.txt'
app = Flask(__name__)

def send_telegram_message(text):
    url = f'https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage'
    data = {'chat_id': TG_CHAT_ID, 'text': text}
    response = requests.post(url, data=data)
    return response.status_code == 200

def load_sent_reviews():
    try:
        with open(SENT_REVIEWS_FILE, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

def save_sent_review(review_id):
    with open(SENT_REVIEWS_FILE, 'a', encoding='utf-8') as f:
        f.write(review_id + '\n')

def parse_reviews_from_url(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    reviews = []
    review_blocks = soup.find_all('div', class_='_1k5soqfl')
    
    for block in review_blocks:
        try:
            name_elem = block.find('span', class_='_16s5yj36')
            name = name_elem.text if name_elem else "Аноним"
            text_elem = block.find('a', class_='_1msln3t') or block.find('a', class_='_1wlx08h')
            text = text_elem.text if text_elem else ""
            date_elem = block.find('div', class_='_1evjsdb')
            date = date_elem.text if date_elem else ""
            review_id = f"{name}_{date}_{text[:30]}"
            reviews.append({
                'id': review_id,
                'name': name,
                'text': text,
                'date': date,
                'url': url
            })
        except:
            continue
    return reviews

def check_new_reviews():
    sent_reviews = load_sent_reviews()
    new_found = False
    for url in PVZ_URLS:
        reviews = parse_reviews_from_url(url)
        for review in reviews:
            if review['id'] not in sent_reviews:
                message = f"📝 НОВЫЙ ОТЗЫВ\n\n👤 {review['name']}\n📅 {review['date']}\n\n💬 {review['text'][:200]}\n\n🔗 {review['url']}"
                send_telegram_message(message)
                save_sent_review(review['id'])
                new_found = True
                time.sleep(1)
        time.sleep(2)
    return new_found

@app.route('/')
def home():
    return "Bot is running"

@app.route('/check')
def manual_check():
    result = check_new_reviews()
    return f"Check completed. New reviews: {result}"

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)