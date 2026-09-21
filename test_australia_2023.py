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
    print("=== ТЕСТОВЫЙ СКРИПТ: Австралия 2023 (Сессия 7787) — Только 2 правила ===", flush=True)

    session_key = 7787  # Гонка Гран-При Австралии 2023

    # 1. Запрашиваем пилотов
    drivers_raw = fetch_json(f"drivers?session_key={session_key}") or []
    drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

    # 2. Запрашиваем 1-й круг
    laps_raw = fetch_json(f"laps?session_key={session_key}") or []
    laps_1 = [l for l in laps_raw if l.get('lap_number') == 1]

    # 3. Рассчитываем медиану Сектора 1
    s1_times = []
    for l in laps_1:
        s1 = l.get('duration_sector_1')
        if s1 is not None:
            try:
                s1_times.append(float(s1))
            except Exception:
                pass

    if not s1_times:
        print("ОШИБКА: Нет данных по Сектору 1 на 1-м круге!", flush=True)
        return

    s1_times.sort()
    median_s1 = s1_times[len(s1_times) // 2]
    print(f"\n---> МЕДИАННОЕ время Сектора 1 на 1-м круге = {median_s1:.3f} сек <---", flush=True)
    print(f"---> Порог детекции (Медиана + 4.0с) = {median_s1 + 4.0:.3f} сек <---\n", flush=True)

    # 4. Выводим таблицу по ВСЕМ пилотам
    print(f"{'№':<4} | {'АКРОНИМ':<6} | {'ИМЯ ПИЛОТА':<20} | {'СЕКТОР 1 (с)':<12} | {'i1_SPEED (км/ч)':<16} | {'ПИТ-ЛЕЙН?':<10}", flush=True)
    print("-" * 80, flush=True)

    laps_1_by_driver = { l.get('driver_number'): l for l in laps_1 if l.get('driver_number') }

    for d_num, d_info in sorted(drivers_dict.items(), key=lambda x: x[0]):
        acronym = d_info.get('name_acronym', 'UNK')
        full_name = d_info.get('full_name', 'Unknown')

        lap_data = laps_1_by_driver.get(d_num, {})
        s1_val = lap_data.get('duration_sector_1')

        # СТРОГО i1_speed (конец 1-го сектора)
        i1_val = lap_data.get('i1_speed')

        s1_str = f"{float(s1_val):.3f}" if s1_val is not None else "НЕТ ДАННЫХ"
        i1_str = f"{float(i1_val):.1f}" if i1_val is not None else "НЕТ ДАННЫХ"

        # Условие 1: Сектор 1 медленнее медианы на +4.0с
        is_pit_by_s1_delta = False
        if s1_val is not None:
            delta = float(s1_val) - median_s1
            if delta > 4.0:
                is_pit_by_s1_delta = True

        # Условие 2: Сектор 1 == None И СТРОГО i1_speed != None
        is_pit_by_missing_s1_with_i1 = (s1_val is None) and (i1_val is not None)

        final_pit = (is_pit_by_s1_delta or is_pit_by_missing_s1_with_i1)
        final_pit_decision = "ДА (PIT)" if final_pit else "НЕТ"

        print(f"{d_num:<4} | {acronym:<6} | {full_name:<20} | {s1_str:<12} | {i1_str:<16} | {final_pit_decision:<10}", flush=True)

if __name__ == "__main__":
    main()
