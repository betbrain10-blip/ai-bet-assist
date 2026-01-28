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


def build_sections(matches):
    corner = []
    value = []
    hot = []

    for m in matches[:20]:

        kickoff = m["utcDate"]
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        kickoff_str = dt.strftime("%d/%m %H:%M")

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        league = m["competition"]["name"]

        value.append({
            "league": league,
            "home": home,
            "away": away,
            "kickoff": kickoff_str,
            "market": "Over 2.5",
            "prob": 0.60,
            "quota_min": 1.6
        })

        corner.append({
            "league": league,
            "home": home,
            "away": away,
            "kickoff": kickoff_str,
            "market": "Over 9.5",
            "prob": 0.58,
            "expected_total": 10.2
        })

    return {
        "corner": corner,
        "value": value,
        "hot": hot
    }


def main():

    if not TOKEN:
        raise Exception("FOOTBALL_DATA_TOKEN non trovato")

    matches = fetch_matches()
    sections = build_sections(matches)

    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%d/%m %H:%M"),
        **sections
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("qr_export.json aggiornato con partite REALI")


if __name__ == "__main__":
    main()
