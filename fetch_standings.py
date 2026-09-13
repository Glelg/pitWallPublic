import urllib.request
import json
import os
import time
from datetime import datetime

BASE_URL = "https://api.openf1.org/v1"

# Международный стандарт ISO 3166-1 (alpha-3 в alpha-2 для иконок флагов)
ISO_ALPHA3_TO_ALPHA2 = {
    "ARG": "ar", "AUS": "au", "AUT": "at", "BEL": "be", "BRA": "br",
    "CAN": "ca", "CHN": "cn", "CZE": "cz", "DEN": "dk", "DNK": "dk",
    "FIN": "fi", "FRA": "fr", "GER": "de", "DEU": "de", "GBR": "gb",
    "HUN": "hu", "IDN": "id", "IND": "in", "ISR": "il", "ITA": "it",
    "JPN": "jp", "MEX": "mx", "MON": "mc", "NED": "nl", "NLD": "nl",
    "NZL": "nz", "POL": "pl", "PRT": "pt", "RUS": "ru", "ESP": "es",
    "SWE": "se", "CHE": "ch", "SUI": "ch", "THA": "th", "USA": "us", "ZAF": "za"
}

def fetch_json(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    print(f"Запрос: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'F1StatsBackend/1.0'})
    try:
        time.sleep(0.2)
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Ошибка запроса {url}: {e}")
        return []

def get_country_flag(country_code_str: str) -> str:
    if not country_code_str:
        return ""
    code = country_code_str.upper().strip()
    return ISO_ALPHA3_TO_ALPHA2.get(code, code.lower()[:2])

def main():
    print("=== Точная сборка с фильтрацией строго по гонкам (Race / Sprint) ===")

    current_year = datetime.utcnow().year
    sessions = fetch_json(f"sessions?year={current_year}")
    if not sessions:
        sessions = fetch_json("sessions")

    if not sessions:
        print("Ошибка: Не удалось получить сессии из OpenF1")
        return

    # 1. Отбираем только очковые сессии (Race и Sprint)
    race_sessions = [s for s in sessions if s.get('session_type') in ['Race', 'Sprint']]
    race_session_keys = set(s['session_key'] for s in race_sessions if 'session_key' in s)

    # 2. Запрашиваем ВСЮ таблицу пилотов
    all_driver_standings = fetch_json("championship_drivers")
    if not all_driver_standings:
        print("Ошибка: Не удалось загрузить championship_drivers")
        return

    # Фильтруем записи таблицы только по гоночным сессиям
    point_standings = [s for s in all_driver_standings if s.get('session_key') in race_session_keys]
    if not point_standings:
        point_standings = all_driver_standings

    # Находим ключи двух последних ГОНОЧНЫХ сессий (N и N-1)
    session_keys = sorted(list(set(item['session_key'] for item in point_standings if 'session_key' in item)))
    if not session_keys:
        return

    latest_key = session_keys[-1]
    prev_key = session_keys[-2] if len(session_keys) > 1 else None

    latest_session_info = next((s for s in sessions if s.get('session_key') == latest_key), {})
    actual_year = latest_session_info.get('year', current_year)
    print(f"Сезон: {actual_year}, Текущая гоночная сессия: {latest_key}, Предыдущая: {prev_key}")

    # Индексируем таблицы
    latest_driver_standings = [s for s in point_standings if s.get('session_key') == latest_key]
    prev_driver_standings_dict = { d['driver_number']: d for d in point_standings if d.get('session_key') == prev_key and 'driver_number' in d } if prev_key else {}

    # Команды
    all_team_standings = fetch_json("championship_teams")
    point_team_standings = [t for t in all_team_standings if t.get('session_key') in race_session_keys] or all_team_standings
    
    latest_team_standings = [t for t in point_team_standings if t.get('session_key') == latest_key]
    prev_team_standings_dict = { t['team_name']: t for t in point_team_standings if t.get('session_key') == prev_key and 'team_name' in t } if prev_key else {}

    # Первая гонка сезона для проверки смены команд
    race_sessions_current_year = [s for s in race_sessions if s.get('year') == actual_year]
    race_sessions_current_year.sort(key=lambda x: x.get('date_start', ''))
    first_key = race_sessions_current_year[0]['session_key'] if race_sessions_current_year else latest_key

    # Составы пилотов
    latest_drivers_raw = fetch_json(f"drivers?session_key={latest_key}")
    first_drivers_raw = fetch_json(f"drivers?session_key={first_key}") if first_key != latest_key else latest_drivers_raw

    latest_drivers = { d['driver_number']: d for d in latest_drivers_raw if 'driver_number' in d }
    first_drivers = { d['driver_number']: d for d in first_drivers_raw if 'driver_number' in d }

    # Обработка пилотов
    enriched_drivers = []
    for standing in latest_driver_standings:
        driver_num = standing.get('driver_number')

        latest_driver = latest_drivers.get(driver_num)
        first_driver = first_drivers.get(driver_num)

        driver_profile = latest_driver or first_driver or {}
        is_inactive = (latest_driver is None)

        full_name = driver_profile.get('full_name') or f"Driver #{driver_num}"
        team_name = driver_profile.get('team_name') or "Formula 1"
        team_colour = driver_profile.get('team_colour') or "808080"
        name_acronym = driver_profile.get('name_acronym') or full_name[:3].upper()

        initial_team = first_driver.get('team_name') if first_driver else None
        current_team = driver_profile.get('team_name')

        previous_team_name = None
        if initial_team and current_team and initial_team.lower() != current_team.lower():
            previous_team_name = initial_team

        position_current = standing.get('position_current', 0)
        points_current = float(standing.get('points_current', 0.0))

        # Вычисляем дельту очков относительно предыдущей ГОНОЧНОЙ сессии
        prev_standing = prev_driver_standings_dict.get(driver_num)
        if prev_standing:
            points_prev = float(prev_standing.get('points_current', points_current))
            position_prev = prev_standing.get('position_current', position_current)
            last_points_gained = points_current - points_prev
            position_change = position_prev - position_current
        else:
            position_start = standing.get('position_start') or position_current
            points_start = float(standing.get('points_start', points_current))
            last_points_gained = points_current - points_start
            position_change = position_start - position_current

        country_code = get_country_flag(driver_profile.get('country_code', ''))

        enriched_drivers.append({
            "position": position_current,
            "driver_number": driver_num,
            "full_name": full_name,
            "name_acronym": name_acronym,
            "team_name": team_name,
            "team_colour": team_colour,
            "points": points_current,
            "last_points_gained": last_points_gained,
            "position_change": position_change,
            "country_code": country_code,
            "is_inactive": is_inactive,
            "previous_team_name": previous_team_name
        })

    enriched_drivers.sort(key=lambda x: x['position'])

    # Обработка команд
    enriched_teams = []
    for team in latest_team_standings:
        team_name = team.get('team_name', 'Unknown')
        position_current = team.get('position_current', 0)
        points_current = float(team.get('points_current', 0.0))

        prev_team = prev_team_standings_dict.get(team_name)
        if prev_team:
            points_prev = float(prev_team.get('points_current', points_current))
            position_prev = prev_team.get('position_current', position_current)
            last_points_gained = points_current - points_prev
            position_change = position_prev - position_current
        else:
            position_start = team.get('position_start') or position_current
            points_start = float(team.get('points_start', points_current))
            last_points_gained = points_current - points_start
            position_change = position_start - position_current

        team_colour = "808080"
        for d in latest_drivers_raw:
            if d.get('team_name', '').lower() == team_name.lower() and d.get('team_colour'):
                team_colour = d.get('team_colour')
                break

        enriched_teams.append({
            "position": position_current,
            "team_name": team_name,
            "team_colour": team_colour,
            "points": points_current,
            "last_points_gained": last_points_gained,  # Исправлено здесь!
            "position_change": position_change
        })

    enriched_teams.sort(key=lambda x: x['position'])

    # Сохранение
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
    file_path = "api/v1/standings.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(final_data, f, ensure_ascii=False, indent=2)

    print(f"=== Исправлено! Файл сохранен: {file_path} ===")

if __name__ == "__main__":
    main()
