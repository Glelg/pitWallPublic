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

def fetch_json(endpoint, retries=6):
    url = f"{BASE_URL}/{endpoint}"
    print(f"Запрос: {url}", flush=True)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*'
    }
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    backoff_delays = [2, 5, 10, 15, 20, 30]

    for attempt in range(retries):
        try:
            time.sleep(1.0)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = backoff_delays[attempt] if attempt < len(backoff_delays) else 30
                print(f"  -> [{e.code} Кулдаун API] Охлаждаем соединение {wait_time} сек... (Попытка {attempt+1}/{retries})", flush=True)
                time.sleep(wait_time)
            elif e.code == 404:
                print(f"  -> [404 Not Found] Результаты недоступны.", flush=True)
                return []
            else:
                print(f"  -> [HTTP Error {e.code}]: {url}", flush=True)
                return []
        except Exception as e:
            print(f"  -> [Ошибка / Таймаут]: {e}", flush=True)
            time.sleep(2)
    return []

def format_lap_time(seconds):
    if seconds is None:
        return ""
    try:
        sec_float = float(seconds)
        mins = int(sec_float // 60)
        remainder = sec_float % 60
        if mins > 0:
            return f"{mins}:{remainder:06.3f}"
        else:
            return f"{remainder:.3f}s"
    except Exception:
        return str(seconds)

def main():
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_year = int(sys.argv[1])
    else:
        target_year = 2024

    print(f"=== Бережная выкачка исторических протоколов за {target_year} год ===", flush=True)

    meetings_raw = fetch_json(f"meetings?year={target_year}") or []
    meetings_dict = { m['meeting_key']: m for m in meetings_raw if 'meeting_key' in m }

    sessions_raw = fetch_json(f"sessions?year={target_year}") or []
    print(f"Сезон: {target_year}, Всего найдено сессий в базе: {len(sessions_raw)}", flush=True)

    current_system_year = datetime.utcnow().year
    now_utc = datetime.utcnow().isoformat()

    if target_year < current_system_year:
        completed_sessions = [s for s in sessions_raw if s.get('session_key')]
    else:
        completed_sessions = [
            s for s in sessions_raw
            if s.get('date_start', '') < now_utc and s.get('session_key')
        ]

    print(f"Сессий для обработки: {len(completed_sessions)}", flush=True)

    out_dir = f"api/v1/results/{target_year}"
    os.makedirs(out_dir, exist_ok=True)

    saved_count = 0
    for idx, s in enumerate(completed_sessions, 1):
        s_key = s.get('session_key')
        m_key = s.get('meeting_key')
        m_info = meetings_dict.get(m_key, {})

        s_name = s.get('session_name', 'Session')

        print(f"[{idx}/{len(completed_sessions)}] Сессия {s_key} ({s_name} - {m_info.get('meeting_name', 'GP')})...", flush=True)

        results_raw = fetch_json(f"session_result?session_key={s_key}") or []
        if not results_raw:
            print(f"  -> [Пусто] Нет результатов для сессии {s_key}", flush=True)
            continue

        drivers_raw = fetch_json(f"drivers?session_key={s_key}") or []
        drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

        def get_sort_pos(r):
            try:
                return int(float(r.get('position', 999)))
            except Exception:
                return 999

        results_raw.sort(key=get_sort_pos)

        formatted_results = []
        for r in results_raw:
            d_num = r.get('driver_number')
            d_info = drivers_dict.get(d_num, {})

            full_name = d_info.get('full_name') or d_info.get('last_name') or f"Driver #{d_num}"
            acronym = d_info.get('name_acronym') or r.get('driver_acronym') or f"#{d_num}"
            team_name = d_info.get('team_name') or r.get('team_name') or "Formula 1"
            country_code = get_country_flag(d_info.get('country_code', ''))

            pos = r.get('position')
            pos_int = int(float(pos)) if pos is not None else None

            duration = r.get('duration')
            gap = r.get('gap_to_leader')
            status = r.get('status', 'FINISHED')

            if status and 'retired' in str(status).lower():
                time_or_retired = str(status).upper()
            elif duration is not None:
                time_or_retired = format_lap_time(duration)
            elif gap is not None:
                time_or_retired = f"+{gap}" if not str(gap).startswith('+') else str(gap)
            else:
                time_or_retired = ""

            gap_to_leader = "LEADER" if pos_int == 1 else (f"+{gap}" if gap and not str(gap).startswith('+') else (str(gap) if gap else ""))

            formatted_results.append({
                "position": pos_int,
                "driver_number": d_num,
                "full_name": full_name,
                "driver_acronym": acronym,
                "team_name": team_name,
                "country_code": country_code,
                "grid_position": r.get('grid_position'),
                "time_or_retired": time_or_retired,
                "gap_to_leader": gap_to_leader,
                "laps_completed": r.get('laps_completed'),
                "points": float(r.get('points', 0.0)),
                "is_fastest_lap": bool(r.get('is_fastest_lap', False)),
                "status": status
            })

        final_data = {
            "metadata": {
                "session_key": s_key,
                "meeting_key": m_key,
                "year": target_year,
                "session_name": s_name,
                "session_type": s.get('session_type', 'Practice'),
                "meeting_name": m_info.get('meeting_name', ''),
                "circuit_name": m_info.get('circuit_short_name', ''),
                "stewards_status": "FINAL",
                "last_updated": datetime.utcnow().isoformat() + "Z"
            },
            "results": formatted_results
        }

        file_path = os.path.join(out_dir, f"{s_key}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        saved_count += 1

    print(f"=== Успех! Создано {saved_count} протоколов в папке {out_dir} ===", flush=True)

if __name__ == "__main__":
    main()