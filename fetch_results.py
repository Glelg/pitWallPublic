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

    print(f"=== Синхронизация результатов сессий {target_year} года (3-Tier Architecture) ===", flush=True)

    meetings_raw = fetch_meetings(target_year)
    meetings_dict = { m['meeting_key']: m for m in meetings_raw if 'meeting_key' in m }

    sessions_raw = fetch_sessions(target_year)
    if not sessions_raw:
        print("Сессий не найдено.", flush=True)
        sys.exit(0)

    now_utc = datetime.utcnow().isoformat()
    completed_sessions = [
        s for s in sessions_raw
        if s.get('date_start', '') < now_utc and s.get('session_key')
    ]

    if not completed_sessions:
        print("Завершенных сессий пока нет.", flush=True)
        sys.exit(0)

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

    synced_keys = set()

    # 1. Синхронизируем последние 5 сессий
    recent_sessions = completed_sessions[-5:]
    for r_session in recent_sessions:
        m_info = meetings_dict.get(r_session.get('meeting_key'), {})
        s_dto = build_session_result_dto(r_session, m_info, target_year, season_drivers, overrides_dict)
        if s_dto:
            save_json_file(os.path.join(out_dir, f"{r_session.get('session_key')}.json"), s_dto)
            synced_keys.add(r_session.get('session_key'))

    # 2. Ротация курсора по историческим сессиям
    cursor_file = "config/results_sync_cursor.json"
    cursor_data = load_json_file(cursor_file, default={"cursor_index": 0})
    cursor_idx = cursor_data.get("cursor_index", 0)

    if cursor_idx >= len(completed_sessions):
        cursor_idx = 0

    target_session = completed_sessions[cursor_idx]
    target_key = target_session.get('session_key')

    if target_key not in synced_keys:
        m_info = meetings_dict.get(target_session.get('meeting_key'), {})
        s_dto = build_session_result_dto(target_session, m_info, target_year, season_drivers, overrides_dict)
        if s_dto:
            save_json_file(os.path.join(out_dir, f"{target_key}.json"), s_dto)

    next_cursor = (cursor_idx + 1) % len(completed_sessions)
    save_json_file(cursor_file, {"cursor_index": next_cursor, "last_synced_session_key": target_key})
    print(f"Курсор ротации передвинут: {cursor_idx} -> {next_cursor}", flush=True)

if __name__ == "__main__":
    main()
