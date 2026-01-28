import requests
import json
import os
from datetime import datetime, timezone

TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")

API_URL = "https://api.football-data.org/v4/matches?status=SCHEDULED"

OUTPUT = "qr_export.json"

def fetch_matches():
    headers = {
        "X-Auth-Token": TOKEN
    }

    r = requests.get(API_URL, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()["matches"]

def main():
    matches = fetch_matches()

    value = []
    corner = []
    hot = []

    for m in matches[:25]:

        kickoff = m["utcDate"]
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        kickoff_str = dt.strftime("%d/%m %H:%M")

        league = m["competition"]["name"]
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]

        event = {
            "league": league,
            "home": home,
            "away": away,
            "kickoff": kickoff_str
        }

        value.append(event)

    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%d/%m %H:%M"),
        "value": value,
        "corner": corner,
        "hot": hot
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("qr_export.json aggiornato con PARTITE REALI")

if __name__ == "__main__":
    main()
