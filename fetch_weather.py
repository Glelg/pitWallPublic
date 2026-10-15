#!/usr/bin/env python3
"""
fetch_weather.py
Fetches weather forecasts from Open-Meteo for the current/upcoming F1 Grand Prix,
generates `api/v1/weather/current.json`, and bakes completed session weather
into `api/v1/f1_schedule_current.json`.
"""

import datetime
import json
import os
import re
import sys
import urllib.request

CIRCUIT_COORDINATES = {
    "sakhir": (26.0325, 50.5106),
    "bahrain": (26.0325, 50.5106),
    "jeddah": (21.6319, 39.1044),
    "melbourne": (-37.8497, 144.968),
    "suzuka": (34.8431, 136.541),
    "shanghai": (31.3389, 121.22),
    "miami": (25.9581, -80.2389),
    "miami gardens": (25.9581, -80.2389),
    "imola": (44.3439, 11.7167),
    "monaco": (43.7347, 7.4206),
    "monte carlo": (43.7347, 7.4206),
    "montreal": (45.5000, -73.5228),
    "montréal": (45.5000, -73.5228),
    "barcelona": (41.5700, 2.2611),
    "spielberg": (47.2197, 14.7647),
    "silverstone": (52.0786, -1.0169),
    "budapest": (47.5830, 19.2505),
    "spa": (50.4372, 5.9714),
    "spa-francorchamps": (50.4372, 5.9714),
    "zandvoort": (52.3888, 4.5409),
    "monza": (45.6156, 9.2811),
    "baku": (40.3725, 49.8533),
    "singapore": (1.2914, 103.864),
    "marina bay": (1.2914, 103.864),
    "austin": (30.1328, -97.6411),
    "mexico city": (19.4042, -99.0907),
    "são paulo": (-23.7036, -46.6997),
    "sao paulo": (-23.7036, -46.6997),
    "las vegas": (36.1147, -115.173),
    "lusail": (25.4900, 51.4542),
    "abu dhabi": (24.4672, 54.6031),
    "yas marina": (24.4672, 54.6031),
    "madrid": (40.4650, -3.6170),
    "sepang": (2.7608, 101.7380),
    "kuala lumpur": (2.7608, 101.7380),
    "malaysia": (2.7608, 101.7380),
}


def get_coordinates(location: str):
    if not location:
        return None
    clean_loc = re.sub(r"\(.*\)", "", location).strip().lower()
    clean_loc = (
        clean_loc.replace("é", "e").replace("ã", "a").replace("ó", "o").replace("-", " ")
    )

    for key, coords in CIRCUIT_COORDINATES.items():
        if key in clean_loc or clean_loc in key:
            return coords
    return None


def parse_iso_datetime(date_str: str) -> datetime.datetime:
    clean_str = date_str[:19]
    return datetime.datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S").replace(
        tzinfo=datetime.timezone.utc
    )


def fetch_open_meteo_forecast(lat: float, lon: float):
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}&"
        f"hourly=temperature_2m,precipitation_probability,weather_code&"
        f"timezone=UTC"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PitwallBackend/1.0"})
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    schedule_file = os.path.join(base_dir, "api", "v1", "f1_schedule_current.json")

    if not os.path.exists(schedule_file):
        print(f"Schedule file not found: {schedule_file}", file=sys.stderr)
        return

    with open(schedule_file, "r", encoding="utf-8") as f:
        schedule_data = json.load(f)

    meetings = schedule_data.get("meetings", [])
    now = datetime.datetime.now(datetime.timezone.utc)

    # Find current active or upcoming meeting
    target_meeting = None
    for meeting in meetings:
        try:
            date_end = parse_iso_datetime(meeting.get("date_end", ""))
            # Active if end date is in future or ended within last 24h
            if date_end + datetime.timedelta(hours=24) >= now:
                target_meeting = meeting
                break
        except Exception:
            continue

    if not target_meeting and meetings:
        target_meeting = meetings[-1]

    current_weather_payload = {
        "meeting_key": target_meeting.get("meeting_key") if target_meeting else None,
        "updated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sessions": {},
    }

    schedule_modified = False

    if target_meeting:
        location = target_meeting.get("location", "")
        coords = get_coordinates(location)

        if coords:
            lat, lon = coords
            try:
                forecast = fetch_open_meteo_forecast(lat, lon)
                hourly = forecast.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                rains = hourly.get("precipitation_probability", [])
                codes = hourly.get("weather_code", [])

                hourly_map = {}
                for i in range(len(times)):
                    t_str = times[i][:13] + ":00"
                    hourly_map[t_str] = {
                        "temp": temps[i],
                        "rain_chance": rains[i],
                        "weather_code": codes[i],
                    }

                for session in target_meeting.get("sessions", []):
                    sess_key = str(session.get("session_key"))
                    date_start_str = session.get("date_start", "")
                    if not date_start_str:
                        continue

                    hour_key = date_start_str[:13] + ":00"
                    weather_item = hourly_map.get(hour_key)

                    if weather_item:
                        current_weather_payload["sessions"][sess_key] = weather_item
                        current_weather_payload["sessions"][hour_key] = weather_item

                        # Lock weather into schedule if session has started
                        sess_start = parse_iso_datetime(date_start_str)
                        if now >= sess_start:
                            new_weather = {
                                "temp": weather_item["temp"],
                                "weather_code": weather_item["weather_code"],
                            }
                            if session.get("weather") != new_weather:
                                session["weather"] = new_weather
                                schedule_modified = True

            except Exception as e:
                print(f"Error fetching weather for {location}: {e}", file=sys.stderr)

    # Also check if any past session in all meetings needs its weather locked from current weather
    for meeting in meetings:
        for session in meeting.get("sessions", []):
            date_start_str = session.get("date_start", "")
            if not date_start_str or "weather" in session:
                continue
            try:
                sess_start = parse_iso_datetime(date_start_str)
                if now >= sess_start:
                    sess_key = str(session.get("session_key"))
                    hour_key = date_start_str[:13] + ":00"
                    item = current_weather_payload["sessions"].get(
                        sess_key
                    ) or current_weather_payload["sessions"].get(hour_key)
                    if item:
                        session["weather"] = {
                            "temp": item["temp"],
                            "weather_code": item["weather_code"],
                        }
                        schedule_modified = True
            except Exception:
                pass

    # Save api/v1/weather/current.json
    weather_dir = os.path.join(base_dir, "api", "v1", "weather")
    os.makedirs(weather_dir, exist_ok=True)
    current_json_path = os.path.join(weather_dir, "current.json")

    with open(current_json_path, "w", encoding="utf-8") as f:
        json.dump(current_weather_payload, f, ensure_ascii=False, indent=2)

    print(f"Successfully generated {current_json_path}")

    # Update f1_schedule_current.json if modified
    if schedule_modified:
        with open(schedule_file, "w", encoding="utf-8") as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=2)
        print(f"Updated schedule with locked weather at {schedule_file}")


if __name__ == "__main__":
    main()
