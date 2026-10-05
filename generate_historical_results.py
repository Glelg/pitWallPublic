import os
import sys
import json
from datetime import datetime

from utils.openf1_client import fetch_meetings, fetch_sessions, fetch_drivers
from utils.session_builder import build_session_result_dto

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

def main():
    target_year = 2026
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_year = int(sys.argv[1])

    print(f"=== ГЕНЕРАЦИЯ ПОЛНОГО СЕЗОНА {target_year} (3-Tier Architecture) ===", flush=True)

    meetings_raw = fetch_meetings(target_year)
    meetings_dict = { m['meeting_key']: m for m in meetings_raw if 'meeting_key' in m }

    sessions_raw = fetch_sessions(target_year)
    print(f"Сезон: {target_year}, Всего найдено сессий: {len(sessions_raw)}", flush=True)

    current_system_year = datetime.utcnow().year
    now_utc = datetime.utcnow().isoformat()

    if target_year < current_system_year:
        completed_sessions = [s for s in sessions_raw if s.get('session_key')]
    else:
        completed_sessions = [
            s for s in sessions_raw
            if s.get('date_start', '') < now_utc and s.get('session_key')
        ]

    season_drivers = {}
    for s in completed_sessions[:3]:
        sk = s.get('session_key')
        if sk:
            d_raw = fetch_drivers(sk)
            for d in d_raw:
                num = d.get('driver_number')
                if num is not None and num not in season_drivers:
                    season_drivers[num] = d

    overrides_file = f"config/overrides/{target_year}.json"
    overrides_dict = load_json_file(overrides_file)

    out_dir = f"api/v1/results/{target_year}"
    os.makedirs(out_dir, exist_ok=True)

    saved_count = 0
    for idx, s in enumerate(completed_sessions, 1):
        s_key = s.get('session_key')
        m_key = s.get('meeting_key')
        m_info = meetings_dict.get(m_key, {})

        print(f"[{idx}/{len(completed_sessions)}] Сессия {s_key}...", flush=True)

        session_dto = build_session_result_dto(s, m_info, target_year, season_drivers, overrides_dict)
        if session_dto:
            file_path = os.path.join(out_dir, f"{s_key}.json")
            save_json_file(file_path, session_dto)
            saved_count += 1

    print(f"=== Успешно создано {saved_count} протоколов в {out_dir} ===", flush=True)

if __name__ == "__main__":
    main()
