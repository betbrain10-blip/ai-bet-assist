import json
from datetime import datetime

# ==========================
# QUI DECIDI TU LE REGOLE
# ==========================
EVENTS = [
    {
        "league": "Serie A",
        "home": "Inter",
        "away": "Juventus",
        "start": "Oggi 20:45",
        "markets": [
            {"label": "Over 1.5", "odd": 1.55},
            {"label": "1X", "odd": 1.65},
            {"label": "DNB 1", "odd": 1.70}
        ]
    },
    {
        "league": "Serie A",
        "home": "Milan",
        "away": "Roma",
        "start": "Oggi 18:00",
        "markets": [
            {"label": "Goal/NoGoal Sì", "odd": 1.75},
            {"label": "Over 2.5", "odd": 1.85}
        ]
    },
    {
        "league": "Premier League",
        "home": "Arsenal",
        "away": "Chelsea",
        "start": "Oggi 16:00",
        "markets": [
            {"label": "Over 2.5", "odd": 1.80},
            {"label": "1X2: 1", "odd": 1.95}
        ]
    }
]

# ==========================
# CREA events.json
# ==========================
data = {
    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "timezone": "Europe/Rome",
    "events": EVENTS
}

with open("events.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("events.json aggiornato")
