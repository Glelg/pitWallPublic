#!/usr/bin/env python3
"""
fill_season_weather.py
Fills historical weather for all completed sessions of a given F1 season (e.g. --year 2026).
Queries Open-Meteo Archive API and bakes temp + weather_code directly into `f1_schedule_{year}.json`.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
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
    "yas island": (24.4672, 54.6031),
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


def fetch_historical_weather(lat: float, lon: float, start_date: str, end_date: str):
    """
    Fetches historical weather for date range (YYYY-MM-DD) from Open-Meteo Archive API.
    Fallback to forecast API if dates are very recent.
    """
    # Archive API for historical data
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?"
        f"latitude={lat}&longitude={lon}&"
        f"start_date={start_date}&end_date={end_date}&"
        f"hourly=temperature_2m,weather_code&"
        f"timezone=UTC"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "PitwallBackend/1.0"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as e:
        # Fallback to forecast endpoint with past_days if recent
        fallback_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}&"
            f"past_days=92&"
            f"hourly=temperature_2m,weather_code&"
            f"timezone=UTC"
        )
        req = urllib.request.Request(
            fallback_url, headers={"User-Agent": "PitwallBackend/1.0"}
        )
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))


def fill_season_weather(year: int, force: bool = False):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    schedule_file = os.path.join(base_dir, "api", "v1", f"f1_schedule_{year}.json")
    current_schedule_file = os.path.join(
        base_dir, "api", "v1", "f1_schedule_current.json"
    )

    if not os.path.exists(schedule_file):
        print(f"Schedule file not found: {schedule_file}", file=sys.stderr)
        return

    with open(schedule_file, "r", encoding="utf-8") as f:
        schedule_data = json.load(f)

    meetings = schedule_data.get("meetings", [])
    now = datetime.datetime.now(datetime.timezone.utc)

    total_sessions_updated = 0

    for meeting in meetings:
        meeting_name = meeting.get("meeting_name", "Unknown GP")
        location = meeting.get("location", "")
        coords = get_coordinates(location)

        if not coords:
            print(
                f"Skipping {meeting_name} ({location}) - coordinates not found",
                file=sys.stderr,
            )
            continue

        sessions = meeting.get("sessions", [])
        if not sessions:
            continue

        # Find sessions that need weather
        completed_sessions = []
        for s in sessions:
            date_start_str = s.get("date_start", "")
            if not date_start_str:
                continue
            sess_time = parse_iso_datetime(date_start_str)
            if sess_time <= now:
                if force or "weather" not in s:
                    completed_sessions.append((s, sess_time))

        if not completed_sessions:
            continue

        # Get date bounds for meeting query (YYYY-MM-DD)
        min_date = min(t for _, t in completed_sessions).strftime("%Y-%m-%d")
        max_date = max(t for _, t in completed_sessions).strftime("%Y-%m-%d")

        lat, lon = coords
        print(f"Fetching weather for {meeting_name} ({min_date} to {max_date})...")

        try:
            weather_resp = fetch_historical_weather(lat, lon, min_date, max_date)
            hourly = weather_resp.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            codes = hourly.get("weather_code", [])

            hourly_map = {}
            for i in range(len(times)):
                t_str = times[i][:13] + ":00"
                hourly_map[t_str] = {
                    "temp": round(temps[i], 1),
                    "weather_code": codes[i],
                }

            updated_in_meeting = 0
            for session, sess_time in completed_sessions:
                hour_key = sess_time.strftime("%Y-%m-%dT%H:00")
                w_item = hourly_map.get(hour_key)
                if w_item:
                    session["weather"] = w_item
                    updated_in_meeting += 1
                    total_sessions_updated += 1

            print(
                f"  Updated {updated_in_meeting}/{len(completed_sessions)} sessions in {meeting_name}"
            )
            time.sleep(0.3)  # Rate limiting courtesy pause

        except Exception as e:
            print(f"  Error fetching weather for {meeting_name}: {e}", file=sys.stderr)

    if total_sessions_updated > 0:
        # Save updated schedule
        with open(schedule_file, "w", encoding="utf-8") as f:
            json.dump(schedule_data, f, ensure_ascii=False, indent=2)
        print(f"\nSaved updated schedule to {schedule_file}")

        current_year = datetime.datetime.now().year
        if year == current_year and os.path.exists(current_schedule_file):
            with open(current_schedule_file, "w", encoding="utf-8") as f:
                json.dump(schedule_data, f, ensure_ascii=False, indent=2)
            print(f"Synced changes to {current_schedule_file}")

        print(
            f"Successfully filled weather for {total_sessions_updated} sessions in season {year}!"
        )
    else:
        print(
            f"\nAll completed sessions in season {year} already have weather filled!"
        )


def main():
    parser = argparse.ArgumentParser(
        description="Fill historical weather for all completed sessions in a given F1 season"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=datetime.datetime.now().year,
        help="Season year (e.g. 2026, 2025, 2024)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch and overwrite weather for sessions that already have weather",
    )
    args = parser.parse_args()

    fill_season_weather(args.year, args.force)


if __name__ == "__main__":
    main()
