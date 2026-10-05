import urllib.request
import urllib.parse
import urllib.error
import json
import re
import time
import ssl
from bs4 import BeautifulSoup

def get_json_with_retry(url, max_retries=5):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'F1StatsAppParser/10.0 (contact@example.com) Python-urllib'
    })
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(max_retries):
        try:
            time.sleep(0.5)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = int(e.headers.get('Retry-After', 3)) + 1
                print(f"  -> [Wiki {e.code}] Пауза {wait_time} сек... (Попытка {attempt+1}/{max_retries})", flush=True)
                time.sleep(wait_time)
            else:
                return None
        except Exception:
            return None
    return None

def fetch_wiki_pit_lane_starters(year, meeting_name, session_type_str):
    """
    Запрашивает Википедию под конкретную сессию ("sprint" или "race").
    Вызывает Википедию каждый раз заново под сессию.
    """
    wiki_title = f"{year}_{meeting_name.replace(' ', '_')}"
    url = f"https://en.wikipedia.org/w/api.php?action=parse&page={urllib.parse.quote(wiki_title)}&prop=text&format=json"

    data = get_json_with_retry(url)
    if not data or 'parse' not in data:
        return set()

    html = data['parse']['text']['*']
    soup = BeautifulSoup(html, 'html.parser')

    target_context = "sprint" if "sprint" in session_type_str.lower() else "race"
    pit_starters = set()

    # Поиск по HTML Таблицам
    for header in soup.find_all(['h2', 'h3', 'h4']):
        header_text = header.get_text().lower()

        context = None
        if 'sprint classification' in header_text or 'sprint result' in header_text:
            context = "sprint"
        elif 'race classification' in header_text or 'race result' in header_text:
            context = "race"

        if context != target_context:
            continue

        table = header.find_next_sibling('table', class_='wikitable')
        if not table:
            table = header.find_next('table', class_='wikitable')

        if not table:
            continue

        header_row = table.find('tr')
        if not header_row:
            continue

        headers = [th.get_text().strip().lower() for th in header_row.find_all(['th', 'td'])]
        if 'grid' not in headers or 'driver' not in headers:
            continue

        grid_idx = headers.index('grid')
        driver_idx = headers.index('driver')

        for row in table.find_all('tr')[1:]:
            cols = row.find_all(['td', 'th'])
            if len(cols) > max(grid_idx, driver_idx):
                grid_text = cols[grid_idx].get_text().strip().upper()
                if 'PL' in grid_text:
                    driver_cell = cols[driver_idx]
                    driver_text = driver_cell.get_text().strip()
                    driver_name = re.sub(r'\[.*?\]', '', driver_text).strip()
                    pit_starters.add(driver_name)

    return pit_starters
