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
    print("=== Архитектурно чистая сборка турнирной таблицы ===")

    # 1. Автоматически определяем текущий календарный год
    current_year = datetime.utcnow().year

    # Запрашиваем сессии актуального года
    sessions = fetch_json(f"sessions?year={current_year}")
    if not sessions:
        sessions = fetch_json("sessions")

    if not sessions:
        print("Ошибка: Не удалось получить сессии из OpenF1")
        return

    latest_session = max(sessions, key=lambda s: s['session_key'])
    latest_key = latest_session['session_key']
    actual_year = latest_session.get('year', current_year)

    print(f"Актуальный сезон: {actual_year}, Последняя сессия: {latest_key}")

    # 2. Запрашиваем таблицы для последней сессии
    all_driver_standings = fetch_json("championship_drivers")
    latest_driver_standings = [s for s in all_driver_standings if s.get('session_key') == latest_key]
    if not latest_driver_standings:
        latest_key = max(s['session_key'] for s in all_driver_standings if 'session_key' in s)
        latest_driver_standings = [s for s in all_driver_standings if s.get('session_key') == latest_key]

    all_team_standings = fetch_json("championship_teams")
    latest_team_standings = [t for t in all_team_standings if t.get('session_key') == latest_key]

    # 3. Находим первую гонку сезона для проверки переходов
    gp_races = [s for s in sessions if s.get('session_type') == 'Race' and s.get('year') == actual_year]
    gp_races.sort(key=lambda x: x.get('date_start', ''))

    first_key = gp_races[0]['session_key'] if gp_races else latest_key

    # 4. Составы первой и последней гонки
    latest_drivers_raw = fetch_json(f"drivers?session_key={latest_key}")
    first_drivers_raw = fetch_json(f"drivers?session_key={first_key}") if first_key != latest_key else latest_drivers_raw

    latest_drivers = { d['driver_number']: d for d in latest_drivers_raw if 'driver_number' in d }
    first_drivers = { d['driver_number']: d for d in first_drivers_raw if 'driver_number' in d }

    # 5. Обработка пилотов (только спортивные данные, без цветов)
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

    # 6. Обработка команд (чистые данные без цветов)
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

    # 7. Сохранение
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

    print(f"=== Полный успех! Сгенерирован чистый файл {file_path} ===")

if __name__ == "__main__":
    main()