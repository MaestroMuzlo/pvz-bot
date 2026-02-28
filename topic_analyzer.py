import numpy as np
from navec import Navec
from collections import Counter
from sklearn.cluster import DBSCAN
import os

print("🔄 Загружаю модель Navec (один раз при старте)...")
path = os.path.join(os.path.dirname(__file__), 'navec_hudlit_v1_12B_500K_300d_100q.tar')
navec = Navec.load(path)

def text_to_vector(text):
    words = text.lower().split()
    vectors = []
    for word in words:
        if word in navec:
            vectors.append(navec[word])
    if not vectors:
        return None
    return np.mean(vectors, axis=0)

def get_topic_from_cluster(cluster_texts):
    all_words = []
    for text in cluster_texts:
        words = text.lower().split()
        all_words.extend(words)
    stopwords = {'очень', 'что', 'это', 'не', 'в', 'на', 'с', 'по', 'как', 'у', 'все', 'было', 'всё', 'только', 'даже', 'нет', 'да', 'ещё', 'уже'}
    filtered = [w for w in all_words if w not in stopwords and len(w) > 2]
    if not filtered:
        return "разное"
    most_common = Counter(filtered).most_common(1)
    return most_common[0][0] if most_common else "разное"

class TopicClassifier:
    def __init__(self, eps=0.5, min_samples=2):
        self.eps = eps
        self.min_samples = min_samples
        self.topic_cache = {}
        self.last_clusters = []

    def predict(self, new_review_text, all_recent_reviews):
        texts = [new_review_text] + all_recent_reviews
        vectors = []
        valid_texts = []
        for t in texts:
            vec = text_to_vector(t)
            if vec is not None:
                vectors.append(vec)
                valid_texts.append(t)

        if len(vectors) < 2:
            return "разное"

        clustering = DBSCAN(eps=self.eps, min_samples=self.min_samples, metric='cosine').fit(vectors)

        new_vec = text_to_vector(new_review_text)
        if new_vec is None:
            return "разное"

        new_index = 0
        label = clustering.labels_[new_index]

        if label == -1:
            return "разное"

        cluster_texts = [valid_texts[i] for i, lbl in enumerate(clustering.labels_) if lbl == label]
        topic = get_topic_from_cluster(cluster_texts)
        return topic