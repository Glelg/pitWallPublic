import urllib.request
import urllib.error
import json
import ssl
import sys
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
    if len(sys.argv) < 3:
        print("ОШИБКА: Укажите год, название Гран-При и (опционально) тип сессии!", flush=True)
        print("Примеры использования:", flush=True)
        print("  python test_gp.py 2023 Australia", flush=True)
        print("  python test_gp.py 2023 Baku Sprint", flush=True)
        print("  python test_gp.py 2024 Austria Sprint", flush=True)
        return

    target_year = sys.argv[1]
    gp_query = sys.argv[2].lower()
    session_query = sys.argv[3].lower() if len(sys.argv) > 3 else "race"

    print(f"=== УНИВЕРСАЛЬНАЯ ДИАГНОСТИКА: {gp_query.upper()} {target_year} ({session_query.upper()}) ===", flush=True)

    # 1. Запрашиваем уикенды года
    meetings_raw = fetch_json(f"meetings?year={target_year}") or []

    target_meeting = next((
        m for m in meetings_raw
        if (gp_query in str(m.get('meeting_name','')).lower() or
            gp_query in str(m.get('country_name','')).lower() or
            gp_query in str(m.get('location','')).lower() or
            gp_query in str(m.get('circuit_short_name','')).lower())
    ), None)

    if not target_meeting:
        print(f"ОШИБКА: Гран-При по запросу '{gp_query}' за {target_year} год не найден!", flush=True)
        return

    m_key = target_meeting.get('meeting_key')
    m_name = target_meeting.get('meeting_name', 'Grand Prix')
    print(f"Найден уикенд: meeting_key = {m_key} ({m_name})", flush=True)

    # 2. Запрашиваем сессии уикенда
    sessions_raw = fetch_json(f"sessions?meeting_key={m_key}") or []

    # Точный отбор Спринт-ГОНКИ (исключая Спринт-Квалификацию/Shootout)
    if session_query == "sprint":
        target_session = next((
            s for s in sessions_raw
            if 'sprint' in str(s.get('session_name','')).lower() and
               'qualifying' not in str(s.get('session_name','')).lower() and
               'shootout' not in str(s.get('session_name','')).lower()
        ), None)
    elif session_query == "race":
        target_session = next((
            s for s in sessions_raw
            if 'race' in str(s.get('session_type','')).lower() and
               'sprint' not in str(s.get('session_name','')).lower()
        ), None)
    else:
        target_session = next((
            s for s in sessions_raw
            if session_query in str(s.get('session_name','')).lower() or
               session_query in str(s.get('session_type','')).lower()
        ), None)

    if not target_session:
        print(f"ОШИБКА: Сессия '{session_query}' для уикенда {m_name} не найдена!", flush=True)
        print("Доступные сессии уикенда:", [s.get('session_name') for s in sessions_raw], flush=True)
        return

    s_key = target_session.get('session_key')
    s_name = target_session.get('session_name', 'Session')
    print(f"Найдена сессия: session_key = {s_key} ({s_name})", flush=True)

    # 3. Запрашиваем пилотов
    drivers_raw = fetch_json(f"drivers?session_key={s_key}") or []
    drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

    # 4. Запрашиваем 1-й круг
    laps_raw = fetch_json(f"laps?session_key={s_key}") or []
    laps_1 = [l for l in laps_raw if l.get('lap_number') == 1]

    # 5. Рассчитываем медиану Сектора 1
    s1_times = []
    for l in laps_1:
        s1 = l.get('duration_sector_1')
        if s1 is not None:
            try:
                s1_times.append(float(s1))
            except Exception:
                pass

    median_s1 = 0.0
    if s1_times:
        s1_times.sort()
        median_s1 = s1_times[len(s1_times) // 2]
        print(f"\n---> МЕДИАННОЕ время Сектора 1 на 1-м круге = {median_s1:.3f} сек <---", flush=True)
        print(f"---> Порог детекции (Медиана + 4.0с) = {median_s1 + 4.0:.3f} сек <---\n", flush=True)
    else:
        print("\n---> НЕТ ДАННЫХ по Сектору 1 на 1-м круге <---\n", flush=True)

    # 6. Выводим таблицу по ВСЕМ пилотам
    print(f"{'№':<4} | {'АКРОНИМ':<6} | {'ИМЯ ПИЛОТА':<20} | {'СЕКТОР 1 (с)':<12} | {'i1_SPEED (км/ч)':<16} | {'ПИТ-ЛЕЙН?':<10}", flush=True)
    print("-" * 90, flush=True)

    laps_1_by_driver = { l.get('driver_number'): l for l in laps_1 if l.get('driver_number') }

    for d_num, d_info in sorted(drivers_dict.items(), key=lambda x: x[0]):
        acronym = d_info.get('name_acronym', 'UNK')
        full_name = d_info.get('full_name', 'Unknown')

        lap_data = laps_1_by_driver.get(d_num, {})
        s1_val = lap_data.get('duration_sector_1')
        i1_val = lap_data.get('i1_speed')

        s1_str = f"{float(s1_val):.3f}" if s1_val is not None else "НЕТ ДАННЫХ"
        i1_str = f"{float(i1_val):.1f}" if i1_val is not None else "НЕТ ДАННЫХ"

        # СТРОГОЕ УСЛОВИЕ 1: Сектор 1 медленнее медианы на +4.0с
        is_pit_by_s1_delta = False
        if s1_val is not None and median_s1 > 0:
            delta = float(s1_val) - median_s1
            if delta > 4.0:
                is_pit_by_s1_delta = True

        # СТРОГОЕ УСЛОВИЕ 2: Сектор 1 == None И СТРОГО i1_speed != None
        is_pit_by_missing_s1_with_i1 = (s1_val is None) and (i1_val is not None)

        final_pit = (is_pit_by_s1_delta or is_pit_by_missing_s1_with_i1)
        final_pit_decision = "ДА (PIT)" if final_pit else "НЕТ"

        print(f"{d_num:<4} | {acronym:<6} | {full_name:<20} | {s1_str:<12} | {i1_str:<16} | {final_pit_decision:<10}", flush=True)

if __name__ == "__main__":
    main()
