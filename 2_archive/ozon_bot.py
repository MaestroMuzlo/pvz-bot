from telegram import Bot
import asyncio

BOT_TOKEN = '8323544415:AAE4y-9wyNhBTdltm2-eds3WTnlDb38bBXw'
CHAT_ID = '5434465388'

async def send_message(text):
    bot = Bot(token=BOT_TOKEN)
    await bot.send_message(chat_id=CHAT_ID, text=text)
    print(f' Отправлено: {text}')

async def main():
    await send_message(' Бот запущен и работает!')
    await send_message(' Ждем ответ от Ozon про API для ПВЗ')

asyncio.run(main())
