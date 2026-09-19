import urllib.request
import urllib.error
import json
import os
import sys
import time
import ssl
from datetime import datetime, timedelta, timezone

from utils.flags import get_country_flag

BASE_URL = "https://api.openf1.org/v1"

def fetch_json(endpoint, retries=5):
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

    backoff_delays = [2, 5, 10, 15, 20]

    for attempt in range(retries):
        try:
            time.sleep(0.5)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = backoff_delays[attempt] if attempt < len(backoff_delays) else 15
                print(f"  -> [{e.code} Лимит] Пауза {wait_time} сек... (Попытка {attempt+1}/{retries})", flush=True)
                time.sleep(wait_time)
            elif e.code == 404:
                print(f"  -> [404 Not Found] Результаты недоступны.", flush=True)
                return []
            else:
                print(f"  -> [HTTP Error {e.code}]: {url}", flush=True)
                return []
        except Exception as e:
            print(f"  -> [Ошибка]: {e}", flush=True)
            return []
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

def load_json_file(filepath, default=None):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default if default is not None else {}

def save_json_file(filepath, data):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sync_single_session_results(session, meeting_info, target_year):
    s_key = session.get('session_key')
    m_key = session.get('meeting_key')
    if not s_key:
        return False

    s_name = session.get('session_name', 'Session')
    print(f"Синхронизация результатов сессии {s_key} ({s_name} - {meeting_info.get('meeting_name', '')})...", flush=True)

    results_raw = fetch_json(f"session_result?session_key={s_key}") or []
    if not results_raw:
        print(f"  -> [Пусто] Результаты для сессии {s_key} еще не опубликованы.", flush=True)
        return False

    drivers_raw = fetch_json(f"drivers?session_key={s_key}") or []
    drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

    def get_sort_pos(r):
        try:
            return int(float(r.get('position', 999)))
        except Exception:
            return 999

    results_raw.sort(key=get_sort_pos)

    # Проверяем ручные переопределения штрафов
    overrides = load_json_file("config/results_overrides.json")
    session_overrides = overrides.get(str(s_key), {})

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

        # Ручные штрафы если есть
        d_override = session_overrides.get(str(d_num))
        if d_override:
            status = d_override.get('status', status)
            pos_int = d_override.get('position', pos_int)

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

    # Статус стюардов: в первые 24 часа "PROVISIONAL", затем "FINAL"
    start_dt_str = session.get('date_start', '')
    stewards_status = "FINAL"
    if start_dt_str:
        try:
            dt_start = datetime.fromisoformat(start_dt_str.replace('Z', '+00:00'))
            if (datetime.now(timezone.utc) - dt_start).total_seconds() < 86400:
                stewards_status = "PROVISIONAL"
        except Exception:
            pass

    final_data = {
        "metadata": {
            "session_key": s_key,
            "meeting_key": m_key,
            "year": target_year,
            "session_name": session.get('session_name', 'Session'),
            "session_type": session.get('session_type', 'Practice'),
            "meeting_name": meeting_info.get('meeting_name', ''),
            "circuit_name": meeting_info.get('circuit_short_name', ''),
            "stewards_status": stewards_status,
            "last_updated": datetime.utcnow().isoformat() + "Z"
        },
        "results": formatted_results
    }

    out_path = f"api/v1/results/{target_year}/{s_key}.json"
    save_json_file(out_path, final_data)
    print(f"=== Протокол сессии {s_key} обновлен: {out_path} ===", flush=True)
    return True

def main():
    target_year = datetime.utcnow().year
    print(f"=== Автоматический умный синхронизатор результатов (сезон {target_year}) ===", flush=True)

    now_dt = datetime.now(timezone.utc)
    now_utc_str = now_dt.isoformat()

    meetings_raw = fetch_json(f"meetings?year={target_year}") or []
    meetings_dict = { m['meeting_key']: m for m in meetings_raw if 'meeting_key' in m }

    sessions_raw = fetch_json(f"sessions?year={target_year}") or []
    completed_sessions = [
        s for s in sessions_raw
        if s.get('date_start', '') < now_utc_str and s.get('session_key')
    ]
    completed_sessions.sort(key=lambda x: x.get('date_start', ''))

    if not completed_sessions:
        print("Нет завершенных сессий в текущем сезоне.", flush=True)
        sys.exit(0)

    # 1. Синхронизируем свежие сессии за последние 7 дней (приоритет)
    seven_days_ago = (now_dt - timedelta(days=7)).isoformat()
    recent_sessions = [
        s for s in completed_sessions
        if s.get('date_start', '') >= seven_days_ago
    ]

    synced_keys = set()
    for r_session in recent_sessions:
        m_info = meetings_dict.get(r_session.get('meeting_key'), {})
        sync_single_session_results(r_session, m_info, target_year)
        synced_keys.add(r_session.get('session_key'))

    # 2. Ротация скользящего курсора для 1 старой сессии
    cursor_file = "config/results_sync_cursor.json"
    cursor_data = load_json_file(cursor_file, default={"cursor_index": 0})
    cursor_idx = cursor_data.get("cursor_index", 0)

    if cursor_idx >= len(completed_sessions):
        cursor_idx = 0

    target_session = completed_sessions[cursor_idx]
    target_key = target_session.get('session_key')

    if target_key not in synced_keys:
        m_info = meetings_dict.get(target_session.get('meeting_key'), {})
        sync_single_session_results(target_session, m_info, target_year)

    next_cursor = (cursor_idx + 1) % len(completed_sessions)
    save_json_file(cursor_file, {"cursor_index": next_cursor, "last_synced_session_key": target_key})
    print(f"Курсор ротации передвинут: {cursor_idx} -> {next_cursor}", flush=True)

if __name__ == "__main__":
    main()