import requests
import time

BOT_TOKEN = '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ'
CHAT_ID = '5434465388'

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': CHAT_ID,
        'text': text
    }
    response = requests.post(url, data=data)
    if response.status_code == 200:
        print(f'✅ Отправлено: {text}')
    else:
        print(f'❌ Ошибка: {response.json()}')

# Тест
send_telegram_message('Бот для ПВЗ работает!')