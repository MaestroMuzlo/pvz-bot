import requests

BOT_TOKEN = '8764632286:AAFRLvCGrXC1siYdZhmxL9gMFzrVqzokAvQ'
CHAT_ID = '5434465388'

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
data = {
    'chat_id': CHAT_ID,
    'text': 'Проверка связи'
}

response = requests.post(url, data=data)
print('Статус:', response.status_code)
print('Ответ:', response.json())