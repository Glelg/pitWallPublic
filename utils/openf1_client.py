import urllib.request
import urllib.error
import json
import time
import ssl

BASE_URL = "https://api.openf1.org/v1"

def fetch_json(endpoint, retries=5):
    url = f"{BASE_URL}/{endpoint}" if not endpoint.startswith("http") else endpoint
    headers = {
        'User-Agent': 'F1StatsAppParser/10.0 (contact@example.com) Python-urllib',
        'Accept': 'application/json, text/plain, */*'
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    backoff_delays = [2, 5, 10, 15, 20]

    for attempt in range(retries):
        try:
            time.sleep(0.3)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = backoff_delays[attempt] if attempt < len(backoff_delays) else 15
                print(f"  -> [OpenF1 {e.code}] Пауза {wait_time} сек... (Попытка {attempt+1}/{retries})", flush=True)
                time.sleep(wait_time)
            elif e.code == 404:
                return []
            else:
                return []
        except Exception:
            time.sleep(1)
            return []
    return []

def fetch_meetings(year):
    return fetch_json(f"meetings?year={year}") or []

def fetch_sessions(year):
    return fetch_json(f"sessions?year={year}") or []

def fetch_session_results(session_key):
    return fetch_json(f"session_result?session_key={session_key}") or []

def fetch_drivers(session_key):
    return fetch_json(f"drivers?session_key={session_key}") or []

def fetch_laps(session_key):
    return fetch_json(f"laps?session_key={session_key}") or []

def fetch_positions(session_key):
    return fetch_json(f"position?session_key={session_key}") or []
