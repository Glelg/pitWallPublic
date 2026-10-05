import re
import sys
import json
from datetime import datetime

from utils.openf1_client import (
    fetch_session_results,
    fetch_drivers,
    fetch_laps,
    fetch_positions,
    fetch_meetings,
    fetch_sessions
)
from utils.wiki_client import fetch_wiki_pit_lane_starters
from utils.flags import get_country_flag

def format_lap_time(val):
    if val is None or val == "":
        return ""
    if isinstance(val, list):
        if not val:
            return ""
        val = val[-1]
    try:
        sec_float = float(val)
        mins = int(sec_float // 60)
        remainder = sec_float % 60
        if mins > 0:
            return f"{mins}:{remainder:06.3f}"
        else:
            return f"{remainder:.3f}s"
    except Exception:
        return str(val)

def format_gap_time(val, pos_int):
    if pos_int == 1:
        return "LEADER"
    if isinstance(val, list):
        if not val:
            return ""
        val = val[-1]
    if val is None or val == "":
        return ""
    try:
        sec_float = float(val)
        if sec_float == 0.0:
            return "LEADER"
        return f"+{sec_float:.3f}s"
    except Exception:
        s = str(val).strip()
        if not s.startswith('+') and s != "LEADER":
            return f"+{s}"
        return s

def extract_time_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [format_lap_time(x) for x in val if x is not None]
    return [format_lap_time(val)]

def match_driver_numbers(wiki_names_set, drivers_dict):
    matched_numbers = set()
    for wiki_name in wiki_names_set:
        w_clean = wiki_name.lower().strip()
        for num, d_info in drivers_dict.items():
            full = (d_info.get('full_name') or '').lower()
            last = (d_info.get('last_name') or '').lower()
            if last and (last in w_clean or w_clean in last):
                matched_numbers.add(num)
            elif full and (full in w_clean or w_clean in full):
                matched_numbers.add(num)
    return matched_numbers

def build_session_result_dto(session, meeting_info, target_year, season_drivers=None, overrides_dict=None):
    s_key = session.get('session_key')
    m_key = session.get('meeting_key')
    if not s_key:
        return None

    s_name = str(session.get('session_name', 'Session'))
    s_type = str(session.get('session_type', 'Practice'))
    m_name = meeting_info.get('meeting_name', '')

    print(f"Сборка результатов сессии: {s_key} ({s_name} - {m_name})...", flush=True)

    # 1. Запрос чистых результатов OpenF1
    results_raw = fetch_session_results(s_key)
    if not results_raw:
        print(f"  -> [Пусто] Нет результатов OpenF1 для сессии {s_key}", flush=True)
        return None

    drivers_raw = fetch_drivers(s_key)
    drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }
    if season_drivers:
        for num, d in season_drivers.items():
            if num not in drivers_dict:
                drivers_dict[num] = d

    is_race_or_sprint = ('race' in s_type.lower() or 'race' in s_name.lower() or 'sprint' in s_name.lower()) and 'qualifying' not in s_name.lower() and 'shootout' not in s_name.lower()
    is_quali = 'qualifying' in s_type.lower() or 'qualifying' in s_name.lower() or 'shootout' in s_name.lower()

    # 2. Вызов Википедии за стартовавшими с пит-лейна
    wiki_pit_numbers = set()
    if is_race_or_sprint and m_name:
        wiki_names = fetch_wiki_pit_lane_starters(target_year, m_name, s_name)
        wiki_pit_numbers = match_driver_numbers(wiki_names, drivers_dict)
        if wiki_pit_numbers:
            print(f"  -> [Wiki PL] Идентифицированы номера пилотов с питлейна: {wiki_pit_numbers}", flush=True)

    # 3. Получение стартовой решетки
    grid_dict = {}
    if is_race_or_sprint:
        pos_raw = fetch_positions(s_key)
        pos_raw.sort(key=lambda x: str(x.get('date', '')))
        for p_item in pos_raw:
            d_n = p_item.get('driver_number')
            p_pos = p_item.get('position')
            if d_n is not None and p_pos is not None and d_n not in grid_dict:
                try:
                    grid_dict[d_n] = int(float(p_pos))
                except Exception:
                    pass

    # 4. Круги и Быстрый круг
    laps_raw = fetch_laps(s_key)
    laps_dict = {}
    fastest_driver_num = None
    valid_lap_times = []

    for l in laps_raw:
        d_num = l.get('driver_number')
        l_num = l.get('lap_number')
        l_dur = l.get('lap_duration')

        if d_num is not None and l_num is not None:
            try:
                laps_dict[d_num] = max(laps_dict.get(d_num, 0), int(l_num))
            except Exception:
                pass

        if is_race_or_sprint and d_num is not None and l_dur is not None:
            try:
                dur_val = float(l_dur)
                if dur_val > 40.0:
                    valid_lap_times.append((d_num, dur_val))
            except Exception:
                pass

    if valid_lap_times:
        valid_lap_times.sort(key=lambda x: x[1])
        fastest_driver_num = valid_lap_times[0][0]

    def get_sort_pos(r):
        pos = r.get('position')
        if pos is not None:
            try:
                return int(float(pos))
            except Exception:
                pass
        return 999

    results_raw.sort(key=get_sort_pos)

    session_overrides = (overrides_dict or {}).get(str(s_key), {})

    formatted_results = []
    processed_driver_nums = set()

    for r in results_raw:
        d_num = r.get('driver_number')
        if d_num is not None:
            processed_driver_nums.add(d_num)
        d_info = drivers_dict.get(d_num, {})

        full_name = d_info.get('full_name') or d_info.get('last_name') or f"Driver #{d_num}"
        acronym = d_info.get('name_acronym') or r.get('driver_acronym') or f"#{d_num}"
        team_name = d_info.get('team_name') or r.get('team_name') or "Formula 1"
        country_code = get_country_flag(d_info.get('country_code', ''))

        pos = r.get('position')
        pos_int = int(float(pos)) if pos is not None else None
        grid_pos = grid_dict.get(d_num) or r.get('grid_position')
        completed_laps = laps_dict.get(d_num) or r.get('laps_completed')

        is_pit_lane = (d_num in wiki_pit_numbers)

        raw_duration = r.get('duration')
        raw_gap = r.get('gap_to_leader')
        status = r.get('status', 'FINISHED')

        is_dsq = bool(r.get('dsq')) or ("DSQ" in str(status).upper()) or ("DISQUALIFIED" in str(status).upper())
        if is_dsq:
            status = "DSQ"

        d_override = session_overrides.get(str(d_num))
        if d_override:
            status = d_override.get('status', status)
            pos_int = d_override.get('position', pos_int)
            if 'is_pit_lane_start' in d_override:
                is_pit_lane = bool(d_override['is_pit_lane_start'])

        q_times = extract_time_list(raw_duration)
        q1_t = q_times[0] if len(q_times) > 0 else None
        q2_t = q_times[1] if len(q_times) > 1 else None
        q3_t = q_times[2] if len(q_times) > 2 else None

        if status and 'retired' in str(status).lower():
            time_or_retired = str(status).upper()
        elif raw_duration is not None:
            time_or_retired = format_lap_time(raw_duration)
        else:
            time_or_retired = ""

        gap_to_leader = format_gap_time(raw_gap, pos_int)
        is_fastest = (d_num == fastest_driver_num) if (is_race_or_sprint and fastest_driver_num is not None) else bool(r.get('is_fastest_lap', False))

        item_dict = {
            "position": pos_int,
            "driver_number": d_num,
            "full_name": full_name,
            "driver_acronym": acronym,
            "team_name": team_name,
            "country_code": country_code,
            "grid_position": grid_pos,
            "grid_penalty": None,
            "is_pit_lane_start": is_pit_lane,
            "time_or_retired": time_or_retired,
            "gap_to_leader": gap_to_leader,
            "laps_completed": completed_laps,
            "points": float(r.get('points', 0.0)),
            "is_fastest_lap": is_fastest,
            "status": status
        }

        if is_quali:
            item_dict["q1_time"] = q1_t
            item_dict["q2_time"] = q2_t
            item_dict["q3_time"] = q3_t

        formatted_results.append(item_dict)

    return {
        "metadata": {
            "session_key": s_key,
            "meeting_key": m_key,
            "year": target_year,
            "session_name": s_name,
            "session_type": s_type,
            "meeting_name": m_name,
            "circuit_name": meeting_info.get('circuit_short_name', ''),
            "stewards_status": "FINAL",
            "last_updated": datetime.utcnow().isoformat() + "Z"
        },
        "results": formatted_results
    }
