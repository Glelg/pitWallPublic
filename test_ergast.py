import urllib.request
import json
import ssl

urls_to_test = [
    "https://api.jolpica.net/ergast/f1/2023/4/results.json",
    "https://jolpica-f1-api.vercel.app/ergast/f1/2023/4/results.json",
    "https://f1-api.vercel.app/api/f1/2023/4/results.json"
]

def main():
    print("=== ТЕСТИРОВАНИЕ ЗЕРКАЛ ERGAST / JOLPICA API ===", flush=True)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for url in urls_to_test:
        print(f"\nЗапрос к зеркалу: {url}", flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                races = data['MRData']['RaceTable']['Races']
                if races:
                    res_list = races[0]['Results']
                    print(f"  -> УСПЕХ! Ответил сервер {url}", flush=True)
                    print(f"\n=== Стартовая решетка (Grid) и финиш (Pos) за Баку 2023: ===", flush=True)
                    for res in res_list:
                        d_num = res['number']
                        d_code = res['Driver']['code']
                        d_name = f"{res['Driver']['givenName']} {res['Driver']['familyName']}"
                        grid = res['grid']
                        pos = res['position']
                        print(f"  Driver #{d_num:<2} ({d_code:<3} - {d_name:<20}): Grid = {grid:<2} | Finish = {pos:<2}", flush=True)
                    return
        except Exception as e:
            print(f"  -> Ошибка зеркала: {e}", flush=True)

    print("\nВсе зеркала недоступны на текущем сетевом подключении.", flush=True)

if __name__ == "__main__":
    main()
