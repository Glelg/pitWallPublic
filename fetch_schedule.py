import urllib.request
import urllib.error
import json
import os
import sys
import time
import ssl
from datetime import datetime

# Общий модуль флагов стран
from utils.flags import get_country_flag

BASE_URL = "https://api.openf1.org/v1"

def is_main_race_session(s):
    """Проверяет, является ли сессия ГЛАВНОЙ воскресной гонкой Гран-При (не Спринтом)"""
    s_type = str(s.get('session_type', '')).lower()
    s_name = str(s.get('session_name', '')).lower()
    return s_type == 'race' and s_name == 'race' and 'sprint' not in s_name

def fetch_json(endpoint, retries=6):
    url = f"{BASE_URL}/{endpoint}"
    print(f"Запрос: {url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    # План пауз при блокировках: 2с, 4с, 8с, 12с, 16с, 20c
    backoff_delays = [2, 4, 8, 12, 16, 20]

    for attempt in range(retries):
        try:
            time.sleep(0.3)
            with urllib.request.urlopen(req, context=ctx) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = backoff_delays[attempt] if attempt < len(backoff_delays) else 20
                print(f"  -> [{e.code} Защита API] Пауза {wait_time} сек... (Попытка {attempt+1}/{retries})")
                time.sleep(wait_time)
            elif e.code == 404:
                print(f"  -> [404 Not Found] Результаты недоступны (гонка отменена или не проводилась).")
                return []
            else:
                print(f"  -> [HTTP Error {e.code}]: {url}")
                return []
        except Exception as e:
            print(f"  -> [Ошибка]: {e}")
            return []
    return []

def update_schedule_status_file(status_msg, success=True):
    """Обновляет статус пульса расписания"""
    os.makedirs("api/v1", exist_ok=True)
    status_file = "api/v1/status.json"
    now_str = datetime.utcnow().isoformat() + "Z"

    current_data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        except Exception:
            pass

    status_payload = {
        "last_checked_at": now_str,
        "schedule_status": status_msg,
        "last_successful_schedule_update": now_str if success else current_data.get("last_successful_schedule_update", now_str),
        "openf1_status": current_data.get("openf1_status", "OK")
    }
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_payload, f, ensure_ascii=False, indent=2)

def main():
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_year = int(sys.argv[1])
        is_custom_year = True
    else:
        target_year = datetime.utcnow().year
        is_custom_year = False

    print(f"=== Защищенная сборка расписания за {target_year} год (только Главные гонки) ===")

    now_utc = datetime.utcnow().isoformat()

    # 1. Запрашиваем уикенды (meetings)
    meetings_raw = fetch_json(f"meetings?year={target_year}")
    if meetings_raw is None:
        print("[ВНИМАНИЕ] OpenF1 недоступен. Фиксируем пульс.")
        update_schedule_status_file("OPENF1_TEMPORARILY_BUSY", success=False)
        sys.exit(0)

    if not meetings_raw:
        meetings_raw = fetch_json("meetings") or []

    if not meetings_raw:
        print("[ВНИМАНИЕ] Не удалось загрузить meetings.")
        update_schedule_status_file("OPENF1_NO_MEETINGS", success=False)
        sys.exit(0)

    season_meetings = meetings_raw
    print(f"Сезон расписания: {target_year}, Всего этапов: {len(season_meetings)}")

    # 2. Запрашиваем все сессии года
    sessions_raw = fetch_json(f"sessions?year={target_year}") or []
    sessions_by_meeting = {}
    for s in sessions_raw:
        m_key = s.get('meeting_key')
        if m_key:
            if m_key not in sessions_by_meeting:
                sessions_by_meeting[m_key] = []
            sessions_by_meeting[m_key].append(s)

    # 3. Находим ВСЕ завершенные ГЛАВНЫЕ ВОСКРЕСНЫЕ ГОНКИ года (исключаем Спринты!)
    completed_races = [
        s for s in sessions_raw
        if is_main_race_session(s) and s.get('date_start', '') < now_utc
    ]
    completed_races.sort(key=lambda x: x.get('date_start', ''))

    # 4. Собираем ПОДИУМЫ ДЛЯ ВСЕХ ЗАВЕРШЕННЫХ ГЛАВНЫХ ГОНОК СЕЗОНА
    podiums_by_session_key = {}
    for race in completed_races:
        race_key = race.get('session_key')
        if not race_key: continue

        results_raw = fetch_json(f"session_result?session_key={race_key}") or []

        # Безопасная фильтрация позиций 1, 2, 3
        podium_raw = []
        for r in results_raw:
            pos = r.get('position')
            try:
                if pos is not None and int(float(pos)) in [1, 2, 3]:
                    podium_raw.append(r)
            except Exception:
                pass

        podium_raw.sort(key=lambda x: int(float(x.get('position', 99))))

        if podium_raw:
            # Выкачиваем пилотов СТРОГО для этой конкретной гонки по ее session_key
            race_drivers_raw = fetch_json(f"drivers?session_key={race_key}") or []
            race_drivers_dict = { d['driver_number']: d for d in race_drivers_raw if 'driver_number' in d }

            podium_list = []
            for p in podium_raw:
                d_num = p.get('driver_number')
                d_info = race_drivers_dict.get(d_num, {})

                acronym = d_info.get('name_acronym') or p.get('driver_acronym') or f"#{d_num}"
                team_name = d_info.get('team_name') or p.get('team_name') or "Formula 1"

                podium_list.append({
                    "position": int(float(p.get('position'))),
                    "driver_number": d_num,
                    "driver_acronym": acronym,
                    "team_name": team_name
                })

            if podium_list:
                podiums_by_session_key[race_key] = podium_list

    # 5. Форматируем уикенды
    formatted_meetings = []
    for m in season_meetings:
        m_key = m.get('meeting_key')
        m_sessions = sessions_by_meeting.get(m_key, [])
        m_sessions.sort(key=lambda x: x.get('date_start', ''))

        date_start = m.get('date_start', '')
        date_end = m.get('date_end', '')
        is_cancelled = bool(m.get('is_cancelled', False))

        if is_cancelled:
            status = "CANCELLED"
        elif date_start and now_utc < date_start:
            status = "UPCOMING"
        elif date_end and now_utc > date_end:
            status = "COMPLETED"
        else:
            status = "LIVE"

        is_testing = "testing" in m.get('meeting_name', '').lower() or "test" in m.get('meeting_name', '').lower()

        formatted_sessions = []
        for s in m_sessions:
            formatted_sessions.append({
                "session_key": s.get('session_key'),
                "session_name": s.get('session_name', 'Session'),
                "session_type": s.get('session_type', 'Practice'),
                "date_start": s.get('date_start', '')
            })

        # Привязываем подиум СТРОГО от Главной воскресной гонки
        top_results = None
        if status == "COMPLETED" and not is_testing:
            race_session = next((s for s in m_sessions if is_main_race_session(s)), None)
            if race_session:
                race_key = race_session.get('session_key')
                top_results = podiums_by_session_key.get(race_key)

        country_code = get_country_flag(m.get('country_code', ''))

        formatted_meetings.append({
            "meeting_key": m_key,
            "meeting_name": m.get('meeting_name', 'Grand Prix'),
            "location": m.get('location', 'Circuit'),
            "country_name": m.get('country_name', ''),
            "country_code": country_code,
            "circuit_name": m.get('circuit_short_name', ''),
            "date_start": date_start,
            "date_end": date_end,
            "status": status,
            "is_cancelled": is_cancelled,
            "is_testing": is_testing,
            "top_results": top_results,
            "sessions": formatted_sessions
        })

    final_data = {
        "metadata": {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "year": target_year,
            "total_meetings": len(formatted_meetings)
        },
        "meetings": formatted_meetings
    }

    os.makedirs("api/v1", exist_ok=True)

    file_path_year = f"api/v1/f1_schedule_{target_year}.json"
    with open(file_path_year, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    if not is_custom_year:
        file_path_current = "api/v1/f1_schedule_current.json"
        with open(file_path_current, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

    update_schedule_status_file("OK", success=True)
    print(f"=== Полный успех! Подиумы Главных гонок сохранены: {file_path_year} ===")

if __name__ == "__main__":
    main()