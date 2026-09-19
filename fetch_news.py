import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import json
import os
import sys
import time
import re
import ssl
from datetime import datetime
from email.utils import parsedate_to_datetime

# Источники свежих новостей Формулы-1
BASE_SOURCES = [
    {"name": "BBC Sport", "url": "https://feeds.bbci.co.uk/sport/formula1/rss.xml"},
    {"name": "Sky Sports", "url": "https://www.skysports.com/rss/12433"},
    {"name": "Motorsport", "url": "https://www.motorsport.com/rss/f1/news/"},
    {"name": "Autosport", "url": "https://www.autosport.com/rss/f1/news/"},
    {"name": "RacingNews365", "url": "https://racingnews365.com/rss"}
]

NOISE_TERMS = ["podcast", "quiz", "gallery", "radio rewind"]
HIGH_IMPACT_TERMS = ["breaking", "official", "confirmed", "winner", "pole", "penalty", "crash"]
STOP_WORDS = {
    "the", "a", "an", "in", "on", "at", "by", "for", "to", "of", "and", "or", "is", "are", "was",
    "be", "been", "from", "with", "as", "about", "after", "over", "it", "this", "that", "how",
    "why", "what", "f1", "formula", "1", "grand", "prix", "gp", "says", "claims", "thinks", "could"
}

def fetch_xml(url, retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*'
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            time.sleep(0.3)
            with urllib.request.urlopen(req, context=ctx) as response:
                return response.read()
        except Exception:
            time.sleep(1)
    return None

def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def parse_rss_feed(source):
    xml_data = fetch_xml(source["url"])
    if not xml_data:
        return []

    items = []
    try:
        root = ET.fromstring(xml_data)
        channel = root.find("channel")
        if channel is None:
            channel = root

        for elem in channel.findall("item"):
            title_elem = elem.find("title")
            link_elem = elem.find("link")
            desc_elem = elem.find("description")
            pub_date_elem = elem.find("pubDate")

            title = clean_html(title_elem.text if title_elem is not None else "")
            link = link_elem.text.strip() if link_elem is not None and link_elem.text else ""
            snippet = clean_html(desc_elem.text if desc_elem is not None else "")

            if not title or not link:
                continue

            pub_ts = time.time()
            if pub_date_elem is not None and pub_date_elem.text:
                try:
                    dt = parsedate_to_datetime(pub_date_elem.text)
                    pub_ts = dt.timestamp()
                except Exception:
                    pass

            image_url = None
            for child in elem:
                if "content" in child.tag or "thumbnail" in child.tag or "enclosure" in child.tag:
                    url_attr = child.attrib.get("url")
                    if url_attr and any(ext in url_attr.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                        image_url = url_attr
                        break

            items.append({
                "id": link,
                "title": title,
                "snippet": snippet,
                "link": link,
                "source_name": source["name"],
                "image_url": image_url,
                "published_at": int(pub_ts * 1000)
            })
    except Exception as e:
        print(f"  -> [XML Parse Error] {source['name']}: {e}")

    return items

def extract_keywords(title):
    words = re.sub(r'[^a-z0-9\s]', ' ', title.lower()).split()
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS}

def is_duplicate(item1, item2):
    k1 = extract_keywords(item1["title"])
    k2 = extract_keywords(item2["title"])
    if not k1 or not k2:
        return False
    intersection = k1.intersection(k2)
    union = k1.union(k2)
    jaccard = len(intersection) / float(len(union))
    return jaccard >= 0.38 or len(intersection) >= 3

def is_noise(item):
    text = f"{item['title']} {item['snippet']}".lower()
    return any(term in text for term in NOISE_TERMS)

def calculate_score(item, now_ms):
    score = 0.0
    title = item["title"].lower()

    age_hours = max(0.0, (now_ms - item["published_at"]) / (1000.0 * 3600.0))
    freshness = max(0.0, 48.0 - age_hours)
    score += freshness

    if any(term in title for term in HIGH_IMPACT_TERMS):
        score += 8.0

    return score

def main():
    print("=== Сборка новостной ленты F1 ===")
    now_ms = int(time.time() * 1000)

    all_items = []
    for src in BASE_SOURCES:
        print(f"Загрузка RSS: {src['name']}")
        items = parse_rss_feed(src)
        all_items.extend(items)

    print(f"Всего найдено новостей из всех источников: {len(all_items)}")

    clean_items = [i for i in all_items if not is_noise(i)]
    clean_items.sort(key=lambda i: calculate_score(i, now_ms), reverse=True)

    unique_items = []
    for item in clean_items:
        if not any(is_duplicate(item, existing) for existing in unique_items):
            unique_items.append(item)

    top_news = unique_items[:22]

    final_data = {
        "metadata": {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "total_news": len(top_news)
        },
        "news": top_news
    }

    os.makedirs("api/v1", exist_ok=True)
    file_path = "api/v1/f1_news_feed.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"=== Успех! Опубликовано {len(top_news)} новостей в {file_path} ===")

if __name__ == "__main__":
    main()