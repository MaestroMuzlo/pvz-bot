import os
import time  # ← ВОТ ЭТО БЫЛО ПРОПУЩЕНО
import requests
from pathlib import Path
from navec import Navec
import numpy as np
from sklearn.cluster import DBSCAN
from collections import Counter

# URL с моделью (можно использовать зеркало или Яндекс.Диск)
MODEL_URL = "https://github.com/natasha/navec/releases/download/v1.0/navec_hudlit_v1_12B_500K_300d_100q.tar"
MODEL_FILENAME = "navec_hudlit_v1_12B_500K_300d_100q.tar"

def download_model():
    """Скачивает модель, если её нет, с повторными попытками"""
    if os.path.exists(MODEL_FILENAME):
        print(f"✅ Модель уже есть: {MODEL_FILENAME}")
        return True
    
    print(f"🔄 Скачиваю модель (300 МБ) с GitHub...")
    
    # Пробуем до 3 раз
    for attempt in range(1, 4):
        try:
            response = requests.get(MODEL_URL, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(MODEL_FILENAME, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Прогресс каждые 10%
                    if total_size > 0:
                        percent = int(100 * downloaded / total_size)
                        if percent % 10 == 0 and downloaded == int(total_size * percent / 100):
                            print(f"   Загружено: {percent}%")
            
            print(f"✅ Модель успешно скачана!")
            return True
            
        except Exception as e:
            print(f"❌ Попытка {attempt} не удалась: {e}")
            if attempt < 3:
                print(f"   Повторная попытка через 5 секунд...")
                time.sleep(5)  # ← ТЕПЕРЬ РАБОТАЕТ, ТАК КАК time ИМПОРТИРОВАН
    
    print("❌ Не удалось скачать модель после 3 попыток")
    return False

# Скачиваем модель при старте
if not download_model():
    print("⚠️ Будет использован упрощённый анализатор!")
    USE_SIMPLE = True
else:
    USE_SIMPLE = False
    print("🔄 Загружаю модель Navec в память...")
    navec = Navec.load(MODEL_FILENAME)
    print("✅ Модель загружена!")

# Упрощённый анализатор как запасной вариант
TOPIC_KEYWORDS = {
    'очередь': ['очеред', 'долго', 'ждать', 'скорость', 'быстро', 'медленно'],
    'персонал': ['сотрудник', 'персонал', 'вежлив', 'груб', 'хам', 'администратор', 'девушка', 'парень'],
    'чистота': ['чист', 'гряз', 'убран', 'светл', 'темн', 'опрятн'],
    'цены': ['цен', 'дорог', 'дешев', 'стоимость', 'копейк'],
    'качество': ['качеств', 'товар', 'продукт', 'брак', 'сломан'],
    'доставка': ['доставк', 'курьер', 'привез', 'опоздан'],
    'парковка': ['парковк', 'машин', 'место', 'припарковаться'],
    'атмосфера': ['атмосфер', 'уютн', 'комфортн', 'музык']
}

def simple_topic_analyzer(text):
    """Запасной вариант, если модель не загрузилась"""
    text_lower = text.lower()
    topic_scores = {}
    
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in text_lower)
        if score > 0:
            topic_scores[topic] = score
    
    if not topic_scores:
        return "разное"
    
    return max(topic_scores, key=topic_scores.get)

def text_to_vector(text):
    """Navec version"""
    if USE_SIMPLE:
        return None
    
    words = text.lower().split()
    vectors = []
    for word in words:
        if word in navec:
            vectors.append(navec[word])
    if not vectors:
        return None
    return np.mean(vectors, axis=0)

def get_topic_from_cluster(cluster_texts):
    """Извлекает тему из кластера"""
    all_words = []
    for text in cluster_texts:
        words = text.lower().split()
        all_words.extend(words)
    
    stopwords = {'очень', 'что', 'это', 'не', 'в', 'на', 'с', 'по', 'как', 'у', 'все'}
    filtered = [w for w in all_words if w not in stopwords and len(w) > 2]
    
    if not filtered:
        return "разное"
    
    return Counter(filtered).most_common(1)[0][0]

class TopicClassifier:
    def __init__(self, eps=0.5, min_samples=2):
        self.eps = eps
        self.min_samples = min_samples
        self.use_navec = not USE_SIMPLE
    
    def predict(self, new_review_text, all_recent_reviews=None):
        """Определяет тему отзыва"""
        
        # Если модель не загрузилась — используем упрощённый вариант
        if not self.use_navec:
            return simple_topic_analyzer(new_review_text)
        
        # Navec version
        if not all_recent_reviews or len(all_recent_reviews) < 2:
            return simple_topic_analyzer(new_review_text)
        
        texts = [new_review_text] + all_recent_reviews
        vectors = []
        valid_texts = []
        
        for t in texts:
            vec = text_to_vector(t)
            if vec is not None:
                vectors.append(vec)
                valid_texts.append(t)
        
        if len(vectors) < 2:
            return simple_topic_analyzer(new_review_text)
        
        clustering = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine').fit(vectors)
        
        new_vec = text_to_vector(new_review_text)
        if new_vec is None:
            return simple_topic_analyzer(new_review_text)
        
        label = clustering.labels_[0]
        if label == -1:
            return simple_topic_analyzer(new_review_text)
        
        cluster_texts = [valid_texts[i] for i, lbl in enumerate(clustering.labels_) if lbl == label]
        return get_topic_from_cluster(cluster_texts)