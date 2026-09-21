import urllib.request
import urllib.error
import json
import ssl
import time

BASE_URL = "https://api.openf1.org/v1"

def fetch_json(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    print(f"[Запрос]: {url}", flush=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        time.sleep(0.3)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  -> Ошибка: {e}", flush=True)
        return []

def main():
    print("=== ДИАГНОСТИКА ЭНДПОИНТОВ /pit И /starting_grid (Баку 2023, Сессия 9078) ===", flush=True)

    session_key = 9078

    # 1. Запрашиваем пилотов
    drivers_raw = fetch_json(f"drivers?session_key={session_key}") or []
    drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

    # 2. Запрашиваем эндпоинт /pit (все заезды/выезды с пит-лейн)
    pit_raw = fetch_json(f"pit?session_key={session_key}") or []
    print(f"\nВсего записей в эндпоинте /pit: {len(pit_raw)}", flush=True)

    # Фильтруем заезды/выезды на 1-м круге
    pit_lap_1 = [p for p in pit_raw if p.get('lap_number') in [0, 1]]
    print(f"Записи в /pit на 1-м круге: {len(pit_lap_1)}", flush=True)
    for p in pit_lap_1:
        d_n = p.get('driver_number')
        d_acronym = drivers_dict.get(d_n, {}).get('name_acronym', f'#{d_n}')
        print(f"  -> Driver #{d_n} ({d_acronym}) | Lap: {p.get('lap_number')} | Pit Duration: {p.get('pit_duration')}", flush=True)

    # 3. Запрашиваем эндпоинт /starting_grid
    grid_raw = fetch_json(f"starting_grid?session_key={session_key}") or []
    print(f"\nВсего записей в /starting_grid: {len(grid_raw)}", flush=True)
    for g in grid_raw:
        d_n = g.get('driver_number')
        d_acronym = drivers_dict.get(d_n, {}).get('name_acronym', f'#{d_n}')
        print(f"  -> Driver #{d_n} ({d_acronym}) | Position: {g.get('position')}", flush=True)

    # 4. Запрашиваем сообщения Race Control
    rc_msgs = fetch_json(f"race_control?session_key={session_key}") or []
    print(f"\nСообщения Race Control с упоминанием PIT / PENALTY / START / OCO / HUL:", flush=True)
    for m in rc_msgs:
        txt = str(m.get('message', '')).upper()
        d_num = m.get('driver_number')
        if d_num in [27, 31] or "PIT" in txt or "31" in txt or "27" in txt or "OCO" in txt or "HUL" in txt:
            print(f"  -> Driver #{d_num} | Msg: {m.get('message')}", flush=True)

if __name__ == "__main__":
    main()
