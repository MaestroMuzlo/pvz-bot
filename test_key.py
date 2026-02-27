import requests

GIS_API_KEY = 'c273c6cd-8df7-4c24-8160-ea286c6cb248'

url = "https://catalog.api.2gis.com/3.0/items"
params = {
    'q': 'Красноярск',
    'key': GIS_API_KEY
}

response = requests.get(url, params=params)
print(f"HTTP статус: {response.status_code}")
print(f"Текст ответа: {response.text[:200]}")