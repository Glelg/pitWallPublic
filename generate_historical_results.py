import urllib.request
import urllib.error
import json
import os
import sys
import time
import ssl
import re
from datetime import datetime

# Общий модуль флагов стран
from utils.flags import get_country_flag

BASE_URL = "https://api.openf1.org/v1"

def fetch_json(endpoint, retries=6):
    url = f"{BASE_URL}/{endpoint}" if not endpoint.startswith("http") else endpoint
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
            time.sleep(0.5)
            with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [429, 401]:
                wait_time = backoff_delays[attempt] if attempt < len(backoff_delays) else 30
                print(f"  -> [{e.code} Кулдаун API] Охлаждаем соединение {wait_time} сек... (Попытка {attempt+1}/{retries})", flush=True)
                time.sleep(wait_time)
            elif e.code == 404:
                return []
            else:
                return []
        except Exception:
            time.sleep(1)
            return []
    return []

def extract_time_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [format_lap_time(x) for x in val if x is not None]
    return [format_lap_time(val)]

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

def get_season_drivers_dict(target_year, completed_sessions):
    season_drivers = {}
    for s in completed_sessions:
        sk = s.get('session_key')
        if sk:
            d_raw = fetch_json(f"drivers?session_key={sk}") or []
            for d in d_raw:
                num = d.get('driver_number')
                if num is not None and num not in season_drivers:
                    season_drivers[num] = d
            if len(season_drivers) >= 22:
                break
    return season_drivers

def main():
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        target_year = int(sys.argv[1])
    else:
        target_year = 2024

    print(f"=== Выкачка протоколов за {target_year} год со 100% быстрыми кругами из памяти ===", flush=True)

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

    season_drivers = get_season_drivers_dict(target_year, completed_sessions)

    out_dir = f"api/v1/results/{target_year}"
    os.makedirs(out_dir, exist_ok=True)

    saved_count = 0
    for idx, s in enumerate(completed_sessions, 1):
        s_key = s.get('session_key')
        m_key = s.get('meeting_key')
        m_info = meetings_dict.get(m_key, {})

        s_name = str(s.get('session_name', 'Session'))
        s_type = str(s.get('session_type', 'Practice'))

        print(f"[{idx}/{len(completed_sessions)}] Сессия {s_key} ({s_name} - {m_info.get('meeting_name', 'GP')})...", flush=True)

        results_raw = fetch_json(f"session_result?session_key={s_key}") or []
        if not results_raw:
            print(f"  -> [Пусто] Нет результатов для сессии {s_key}", flush=True)
            continue

        drivers_raw = fetch_json(f"drivers?session_key={s_key}") or []
        drivers_dict = { d['driver_number']: d for d in drivers_raw if 'driver_number' in d }

        if season_drivers:
            for num, d in season_drivers.items():
                if num not in drivers_dict:
                    drivers_dict[num] = d

        is_race_or_sprint = ('race' in s_type.lower() or 'race' in s_name.lower() or 'sprint' in s_name.lower()) and 'qualifying' not in s_name.lower() and 'shootout' not in s_name.lower()
        is_quali = 'qualifying' in s_type.lower() or 'qualifying' in s_name.lower() or 'shootout' in s_name.lower()

        # --- ДЕТЕКЦИЯ ПИТ-ЛЕЙН ПО ТЕЛЕМЕТРИИ ---
        pit_lane_starters_by_telemetry = set()
        if is_race_or_sprint:
            laps_1 = fetch_json(f"laps?session_key={s_key}&lap_number=1") or []
            s1_times = [float(l['duration_sector_1']) for l in laps_1 if l.get('duration_sector_1') is not None]

            if s1_times:
                s1_times.sort()
                median_s1 = s1_times[len(s1_times) // 2]
                for l in laps_1:
                    d_num = l.get('driver_number')
                    s1_val = l.get('duration_sector_1')
                    i1_val = l.get('i1_speed')

                    if d_num is not None:
                        is_pit_by_s1_delta = False
                        if s1_val is not None:
                            try:
                                if float(s1_val) > (median_s1 + 5.0):
                                    is_pit_by_s1_delta = True
                            except Exception:
                                pass

                        is_pit_by_missing_s1_with_i1 = (s1_val is None) and (i1_val is not None)

                        if is_pit_by_s1_delta or is_pit_by_missing_s1_with_i1:
                            pit_lane_starters_by_telemetry.add(d_num)

        # --- СТАРТОВАЯ РЕШЕТКА ---
        grid_dict = {}
        if is_race_or_sprint:
            pos_raw = fetch_json(f"position?session_key={s_key}") or []
            pos_raw.sort(key=lambda x: str(x.get('date', '')))
            for p_item in pos_raw:
                d_n = p_item.get('driver_number')
                p_pos = p_item.get('position')
                if d_n is not None and p_pos is not None:
                    if d_n not in grid_dict:
                        try:
                            grid_dict[d_n] = int(float(p_pos))
                        except Exception:
                            pass

        # --- КВАЛИФИКАЦИОННЫЕ ШТРАФЫ ДЛЯ КВАЛИФИКАЦИИ ---
        quali_penalties_dict = {}
        if is_quali and m_key:
            m_sessions = [sess for sess in sessions_raw if sess.get('meeting_key') == m_key]
            is_sprint_quali = 'sprint' in s_name.lower() or 'shootout' in s_name.lower()

            if is_sprint_quali:
                target_sess = next((sess for sess in m_sessions if 'sprint' in str(sess.get('session_name','')).lower() and 'qualifying' not in str(sess.get('session_name','')).lower() and 'shootout' not in str(sess.get('session_name','')).lower()), None)
            else:
                target_sess = next((sess for sess in m_sessions if ('race' in str(sess.get('session_type','')).lower() or 'grand prix' in str(sess.get('session_name','')).lower()) and 'sprint' not in str(sess.get('session_name','')).lower()), None)

            if target_sess:
                r_key = target_sess.get('session_key')
                r_pos_raw = fetch_json(f"position?session_key={r_key}") or []
                r_pos_raw.sort(key=lambda x: str(x.get('date', '')))
                r_grid_dict = {}
                for p_item in r_pos_raw:
                    d_n = p_item.get('driver_number')
                    p_pos = p_item.get('position')
                    if d_n is not None and p_pos is not None and d_n not in r_grid_dict:
                        try: r_grid_dict[d_n] = int(float(p_pos))
                        except Exception: pass

                for r_item in results_raw:
                    d_n = r_item.get('driver_number')
                    q_pos = r_item.get('position')
                    if d_n is not None and q_pos is not None:
                        try:
                            q_pos_int = int(float(q_pos))
                            r_grid_pos = r_grid_dict.get(d_n)
                            if r_grid_pos is not None and r_grid_pos > q_pos_int:
                                quali_penalties_dict[d_n] = r_grid_pos - q_pos_int
                        except Exception:
                            pass
                        except Exception:
                            pass

        # --- ПРОЙДЕННЫЕ КРУГИ И ПОИСК БЫСТРОГО КРУГА В ПАМЯТИ (0 ЗАПРОСОВ В СЕТЬ) ---
        laps_raw = fetch_json(f"laps?session_key={s_key}") or []
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
                    if dur_val > 40.0: # Фильтр валидных кругов Ф1
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

        overrides_file = f"config/overrides/{target_year}.json"
        if os.path.exists(overrides_file):
            overrides = load_json_file(overrides_file)
        else:
            overrides = load_json_file("config/results_overrides.json")
        session_overrides = overrides.get(str(s_key), {})

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

            is_pit_lane = (d_num in pit_lane_starters_by_telemetry)

            grid_penalty = None
            if is_quali:
                grid_penalty = quali_penalties_dict.get(d_num)

            raw_duration = r.get('duration')
            raw_gap = r.get('gap_to_leader')
            status = r.get('status', 'FINISHED')

            is_dsq = bool(r.get('dsq')) or ("DSQ" in str(status).upper()) or ("DISQUALIFIED" in str(status).upper())
            if is_dsq:
                status = "DSQ"
            elif is_pit_lane and not status:
                status = "PIT LANE"

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

            # Точный подчет Быстрого круга
            is_fastest = (d_num == fastest_driver_num) if (is_race_or_sprint and fastest_driver_num is not None) else bool(r.get('is_fastest_lap', False))

            item_dict = {
                "position": pos_int,
                "driver_number": d_num,
                "full_name": full_name,
                "driver_acronym": acronym,
                "team_name": team_name,
                "country_code": country_code,
                "grid_position": grid_pos,
                "grid_penalty": grid_penalty,
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

        # --- АВТОДЕТЕКЦИЯ НЕЗАЯВЛЕННЫХ В ПРОТОКОЛЕ ПИЛОТОВ (DNS / NO TIME) ---
        missing_driver_nums = set(drivers_dict.keys()) - processed_driver_nums
        for m_num in missing_driver_nums:
            d_info = drivers_dict.get(m_num, {})
            full_name = d_info.get('full_name') or d_info.get('last_name') or f"Driver #{m_num}"
            acronym = d_info.get('name_acronym') or f"#{m_num}"
            team_name = d_info.get('team_name') or "Formula 1"
            country_code = get_country_flag(d_info.get('country_code', ''))

            default_status = "NO TIME" if is_quali else "DNS"
            status = default_status
            pos_int = None
            is_pit_lane = False

            d_override = session_overrides.get(str(m_num))
            if d_override:
                status = d_override.get('status', status)
                pos_int = d_override.get('position', pos_int)
                if 'is_pit_lane_start' in d_override:
                    is_pit_lane = bool(d_override['is_pit_lane_start'])

            time_or_retired = status

            item_dict = {
                "position": pos_int,
                "driver_number": m_num,
                "full_name": full_name,
                "driver_acronym": acronym,
                "team_name": team_name,
                "country_code": country_code,
                "grid_position": grid_dict.get(m_num),
                "grid_penalty": None,
                "is_pit_lane_start": is_pit_lane,
                "time_or_retired": time_or_retired,
                "gap_to_leader": "",
                "laps_completed": laps_dict.get(m_num, 0),
                "points": 0.0,
                "is_fastest_lap": False,
                "status": status
            }

            if is_quali:
                item_dict["q1_time"] = None
                item_dict["q2_time"] = None
                item_dict["q3_time"] = None

            formatted_results.append(item_dict)

        final_data = {
            "metadata": {
                "session_key": s_key,
                "meeting_key": m_key,
                "year": target_year,
                "session_name": s_name,
                "session_type": s_type,
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

    print(f"=== Успех! Создано {saved_count} точнейших протоколов в папке {out_dir} ===", flush=True)

if __name__ == "__main__":
    main()
