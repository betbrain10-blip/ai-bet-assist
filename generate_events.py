import json
import os
import requests
from datetime import datetime, timezone

TOKEN = os.getenv("FOOTBALL_DATA_TOKEN")

OUTPUT = "qr_export.json"

BASE_URL = "https://api.football-data.org/v4"

HEADERS = {
    "X-Auth-Token": TOKEN
}

# Campionati target
COMPETITIONS = {
    "SA": "Serie A",
    "PL": "Premier League",
    "PD": "La Liga",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1"
}


def fetch_upcoming_matches():
    url = f"{BASE_URL}/matches?status=SCHEDULED"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()["matches"]


def build_sections(matches):
    corner = []
    value = []
    hot = []

    now = datetime.now(timezone.utc)

    for m in matches:

        kickoff = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))

        if kickoff < now:
            continue

        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        league = COMPETITIONS.get(
            m["competition"]["code"],
            m["competition"]["name"]
        )

        kickoff_str = kickoff.strftime("%d/%m %H:%M")

        event = {
            "league": league,
            "home": home,
            "away": away,
            "kickoff": kickoff_str,
            "match": f"{home} - {away}",
        }

        # ---------- MOCK LOGICA AI (per ora) ----------
        prob = round(0.58 + (hash(home + away) % 10) / 100, 2)

        event_corner = {
            **event,
            "market": "Over 9.5",
            "prob": prob,
            "expected_total": round(9 + prob * 3, 1)
        }

        event_value = {
            **event,
            "market": "Over 2.5",
            "prob": prob,
            "quota_min": 1.60
        }

        # Distribuzione
        corner.append(event_corner)

        if prob >= 0.60:
            value.append(event_value)

        if prob >= 0.63:
            hot.append(event_value)

        if len(corner) >= 6:
            break

    return {
        "corner": corner,
        "value": value,
        "hot": hot
    }


def main():

    if not TOKEN:
        raise RuntimeError("FOOTBALL_DATA_TOKEN mancante")

    matches = fetch_upcoming_matches()

    sections = build_sections(matches)

    data = {
        "updated_at": datetime.now().strftime("%d/%m %H:%M"),
        "corner": sections["corner"],
        "value": sections["value"],
        "hot": sections["hot"]
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("✅ qr_export.json aggiornato con partite REALI")


if __name__ == "__main__":
    main()
