import os
import json
import requests
from datetime import datetime, timezone

OUTPUT = "qr_export.json"

API_URL = "https://api.football-data.org/v4/matches"

TOKEN = os.getenv("FOOTBALL_DATA_TOKEN")


def fetch_matches():
    if not TOKEN:
        raise Exception("FOOTBALL_DATA_TOKEN mancante")

    headers = {
        "X-Auth-Token": TOKEN
    }

    params = {
        "status": "SCHEDULED"
    }

    res = requests.get(API_URL, headers=headers, params=params, timeout=20)
    res.raise_for_status()

    return res.json()["matches"]


def build_sections(matches):
    corner = []
    value = []
    hot = []

    now = datetime.now(timezone.utc)

    for m in matches[:20]:

        kickoff = m["utcDate"][:16].replace("T", " ")

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        league = m["competition"]["name"]

        event = {
            "home": home,
            "away": away,
            "league": league,
            "kickoff": kickoff,
            "market": "Over 2.5",
            "prob": 0.60,
            "quota_min": 1.6
        }

        value.append(event)

    return {
        "corner": corner,
        "value": value,
        "hot": hot
    }


def main():
    print("📡 Download matches...")

    matches = fetch_matches()
    sections = build_sections(matches)

    data = {
        "updated_at": datetime.now().strftime("%d/%m %H:%M"),
        "corner": sections["corner"],
        "value": sections["value"],
        "hot": sections["hot"]
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("✅ qr_export.json aggiornato")


if __name__ == "__main__":
    main()
