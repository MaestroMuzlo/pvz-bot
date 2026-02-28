import asyncio
from ozonapi import SellerAPI

async def test_connection():
    print("🔍 Проверка подключения к Ozon...")
    
    # ВСТАВЬ СВОИ ДАННЫЕ СЮДА (из кабинета Ozon)
    CLIENT_ID = "твой_client_id"
    API_KEY = "твой_api_key"
    
    try:
        async with SellerAPI(
            client_id=CLIENT_ID,
            api_key=API_KEY
        ) as api:
            # Пробуем получить информацию о продавце
            info = await api.seller_info()
            print("✅ УСПЕХ! Подключение работает!")
            print(f"📦 Компания: {info.company.name}")
            print(f"📧 Email: {info.company.email}")
            
    except Exception as e:
        print("❌ ОШИБКА подключения:")
        print(e)

asyncio.run(test_connection())