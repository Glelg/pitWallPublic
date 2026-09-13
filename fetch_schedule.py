import urllib.request
import urllib.error
import json
import os
import sys
import time
import ssl
from datetime import datetime

# Импортируем наш общий модуль флагов из utils
from utils.flags import get_country_flag

BASE_URL = "https://api.openf1.org/v1"

def update_status_file(status_msg, success=True):
    """Обновляет пульс бэкенда при каждом запуске"""
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
        "openf1_status": status_msg,
        "last_successful_standings_update": now_str if success else current_data.get("last_successful_standings_update", now_str)
    }
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump(status_payload, f, ensure_ascii=False, indent=2)

def fetch_json(endpoint):
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

    try:
        time.sleep(0.3)
        with urllib.request.urlopen(req, context=ctx) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        print(f"  -> [OpenF1 Ошибка {e.code}]: Сервер недоступен.")
        return None
    except Exception as e:
        print(f"  -> [Сетевая ошибка]: {e}")
        return None

def main():
    print("=== Чистая сборка с фиксацией пульса через utils.flags ===")

    current_year = datetime.utcnow().year

    sessions = fetch_json(f"sessions?year={current_year}")
    if sessions is None:
        print("[ВНИМАНИЕ] OpenF1 заблокирован. Фиксируем пульс проверки.")
        update_status_file("OPENF1_TEMPORARILY_BUSY", success=False)
        sys.exit(0)

    if not sessions:
        sessions = fetch_json("sessions") or []

    if not sessions:
        print("[ВНИМАНИЕ] Не удалось получить сессии. Фиксируем пульс.")
        update_status_file("OPENF1_NO_SESSIONS", success=False)
        sys.exit(0)

    latest_session = max(sessions, key=lambda s: s['session_key'])
    latest_key = latest_session['session_key']
    actual_year = latest_session.get('year', current_year)

    print(f"Актуальный сезон: {actual_year}, Последняя сессия: {latest_key}")

    all_driver_standings = fetch_json("championship_drivers")
    if not all_driver_standings:
        print("[ВНИМАНИЕ] Таблица пилотов недоступна. Фиксируем пульс.")
        update_status_file("OPENF1_STANDINGS_UNAVAILABLE", success=False)
        sys.exit(0)

    latest_driver_standings = [s for s in all_driver_standings if s.get('session_key') == latest_key]
    if not latest_driver_standings:
        latest_key = max(s['session_key'] for s in all_driver_standings if 'session_key' in s)
        latest_driver_standings = [s for s in all_driver_standings if s.get('session_key') == latest_key]

    all_team_standings = fetch_json("championship_teams") or []
    latest_team_standings = [t for t in all_team_standings if t.get('session_key') == latest_key]

    gp_races = [s for s in sessions if s.get('session_type') == 'Race' and s.get('year') == actual_year]
    gp_races.sort(key=lambda x: x.get('date_start', ''))

    first_key = gp_races[0]['session_key'] if gp_races else latest_key

    latest_drivers_raw = fetch_json(f"drivers?session_key={latest_key}") or []
    first_drivers_raw = fetch_json(f"drivers?session_key={first_key}") if first_key != latest_key else latest_drivers_raw
    if first_drivers_raw is None: first_drivers_raw = []

    latest_drivers = { d['driver_number']: d for d in latest_drivers_raw if 'driver_number' in d }
    first_drivers = { d['driver_number']: d for d in first_drivers_raw if 'driver_number' in d }

    enriched_drivers = []
    for standing in latest_driver_standings:
        driver_num = standing.get('driver_number')

        latest_driver = latest_drivers.get(driver_num)
        first_driver = first_drivers.get(driver_num)

        driver_profile = latest_driver or first_driver or {}
        is_inactive = (latest_driver is None)

        full_name = driver_profile.get('full_name') or f"Driver #{driver_num}"
        team_name = driver_profile.get('team_name') or "Formula 1"
        name_acronym = driver_profile.get('name_acronym') or full_name[:3].upper()

        initial_team = first_driver.get('team_name') if first_driver else None
        current_team = driver_profile.get('team_name')

        previous_team_name = None
        if initial_team and current_team and initial_team.lower() != current_team.lower():
            previous_team_name = initial_team

        position_current = standing.get('position_current', 0)
        position_start = standing.get('position_start') or position_current

        points_current = float(standing.get('points_current', 0.0))
        points_start = float(standing.get('points_start', points_current))

        country_code = get_country_flag(driver_profile.get('country_code', ''))

        enriched_drivers.append({
            "position": position_current,
            "driver_number": driver_num,
            "full_name": full_name,
            "name_acronym": name_acronym,
            "team_name": team_name,
            "points": points_current,
            "last_points_gained": points_current - points_start,
            "position_change": position_start - position_current,
            "country_code": country_code,
            "is_inactive": is_inactive,
            "previous_team_name": previous_team_name
        })

    enriched_drivers.sort(key=lambda x: x['position'])

    enriched_teams = []
    for team in latest_team_standings:
        team_name = team.get('team_name', 'Unknown')
        position_current = team.get('position_current', 0)
        position_start = team.get('position_start') or position_current

        points_current = float(team.get('points_current', 0.0))
        points_start = float(team.get('points_start', points_current))

        enriched_teams.append({
            "position": position_current,
            "team_name": team_name,
            "points": points_current,
            "last_points_gained": points_current - points_start,
            "position_change": position_start - position_current
        })

    enriched_teams.sort(key=lambda x: x['position'])

    if not enriched_drivers:
        print("[ВНИМАНИЕ] Список пилотов пуст. Фиксируем пульс.")
        update_status_file("OPENF1_EMPTY_RESPONSE", success=False)
        sys.exit(0)

    final_data = {
        "metadata": {
            "last_updated": datetime.utcnow().isoformat() + "Z",
            "session_key": latest_key,
            "year": actual_year
        },
        "driver_standings": enriched_drivers,
        "team_standings": enriched_teams
    }

    os.makedirs("api/v1", exist_ok=True)
    file_path = "api/v1/f1_championship_standings.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    update_status_file("OK", success=True)
    print(f"=== Успешно! Файл обновлен: {file_path} ===")

if __name__ == "__main__":
    main()