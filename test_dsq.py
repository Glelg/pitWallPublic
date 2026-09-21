import urllib.request
import json
import ssl

BASE_URL = "https://api.openf1.org/v1"

def fetch_json(endpoint):
    url = f"{BASE_URL}/{endpoint}"
    print(f"[Запрос]: {url}", flush=True)
    headers = {'User-Agent': 'Mozilla/5.0'}
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  -> Ошибка: {e}", flush=True)
        return []

def main():
    print("=== ИНСПЕКЦИЯ ЛАС-ВЕГАСА 2025 В OPENF1 ===", flush=True)

    sessions_2025 = fetch_json("sessions?year=2025") or []
    print(f"Всего найдено сессий за 2025 год: {len(sessions_2025)}", flush=True)

    vegas_2025 = [s for s in sessions_2025 if 'vegas' in str(s.get('location','')).lower() or 'vegas' in str(s.get('circuit_short_name','')).lower() or 'vegas' in str(s.get('meeting_name','')).lower()]

    if not vegas_2025:
        print("Сессии Лас-Вегаса 2025 года не найдены в OpenF1.", flush=True)
        return

    for s in vegas_2025:
        s_key = s.get('session_key')
        s_name = s.get('session_name')
        print(f"\n--- 2025 Vegas: session_key = {s_key} ({s_name}) ---", flush=True)
        results = fetch_json(f"session_result?session_key={s_key}") or []
        for r in results:
            d_num = r.get('driver_number')
            pos = r.get('position')
            status = r.get('status')
            dsq = r.get('dsq')
            dnf = r.get('dnf')
            print(f"  Driver #{d_num:<2}: Position = {str(pos):<4} | Status = '{status}' | DSQ = {dsq} | DNF = {dnf}", flush=True)

if __name__ == "__main__":
    main()
