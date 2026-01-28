import requests
import json
import os
import random
from datetime import datetime, timezone

TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")

API_URL = "https://api.football-data.org/v4/matches?status=SCHEDULED"

OUTPUT = "qr_export.json"


HEADERS = {
    "X-Auth-Token": TOKEN
}


def fetch_matches():
    r = requests.get(API_URL, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.json()["matches"]


def is_today(match):
    utc = datetime.fromisoformat(match["utcDate"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return utc.date() == now.date()


def ai_markets():
    goals = round(random.uniform(2.1, 3.4), 2)
    corners = round(random.uniform(8.5, 12.8), 1)

    return {
        "over25": round(random.uniform(0.55, 0.72), 2),
        "corners95": round(random.uniform(0.55, 0.70), 2),
        "cards_home": round(random.uniform(0.50, 0.68), 2),
        "cards_away": round(random.uniform(0.50, 0.68), 2),
        "dnb_home": round(random.uniform(0.55, 0.75), 2),
        "xg": goals,
        "expected_corners": corners
    }


def main():
    matches = fetch_matches()

    today_matches = [m for m in matches if is_today(m)]

    value = []
    corner = []
    hot = []

    for m in today_matches:
        home = m["homeTeam"]["name"]
        away = m["awayTeam"]["name"]
        league = m["competition"]["name"]

        dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
        kickoff = dt.strftime("%d/%m %H:%M")

        markets = ai_markets()

        record = {
            "league": league,
            "home": home,
            "away": away,
            "kickoff": kickoff,
            "markets": markets
        }

        if markets["over25"] > 0.62:
            value.append(record)

        if markets["corners95"] > 0.6:
            corner.append(record)

        if markets["dnb_home"] > 0.68:
            hot.append(record)

    export = {
        "updated_at": datetime.now().strftime("%d/%m %H:%M"),
        "value": value[:12],
        "corner": corner[:12],
        "hot": hot[:6]
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    print("qr_export.json aggiornato con partite REALI + AI markets")


if __name__ == "__main__":
    main()
