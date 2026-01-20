import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

# =========================
# CONFIG
# =========================
TZ = ZoneInfo("Europe/Rome")

# Fasce orarie (ora locale Italia)
MORNING_START = 6
MORNING_END = 12     # escluso
AFTERNOON_START = 12
AFTERNOON_END = 18   # escluso
EVENING_START = 18
EVENING_END = 24     # escluso

PER_SLOT = 5  # 5 mattina + 5 pomeriggio + 5 sera

# Competizioni principali europee (Football-Data codes)
ALLOW_COMP_CODES = {
    "CL",   # Champions League
    "EL",   # Europa League
    "PL",   # Premier League
    "PD",   # LaLiga
    "SA",   # Serie A
    "BL1",  # Bundesliga
    "FL1",  # Ligue 1
    "DED",  # Eredivisie
    "PPL",  # Primeira Liga
}

LOOKAHEAD_DAYS = 2
OUT_FILE = "events.json"


def _env_token() -> str:
    t = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN missing in env (GitHub Secrets).")
    return t


def _football_data_get(url: str, token: str, params=None) -> dict:
    headers = {"X-Auth-Token": token}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _format_start(dt_rome: datetime) -> str:
    now = datetime.now(TZ)
    if dt_rome.date() == now.date():
        day = "Oggi"
    elif dt_rome.date() == (now.date() + timedelta(days=1)):
        day = "Domani"
    else:
        wk = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
        day = wk[dt_rome.weekday()]
    return f"{day} {dt_rome.strftime('%H:%M')}"


def _slot_of(dt_rome: datetime) -> str | None:
    h = dt_rome.hour
    if MORNING_START <= h < MORNING_END:
        return "mattina"
    if AFTERNOON_START <= h < AFTERNOON_END:
        return "pomeriggio"
    if EVENING_START <= h < EVENING_END:
        return "sera"
    return None


def main():
    token = _env_token()

    today = datetime.now(TZ).date()
    date_from = today
    date_to = today + timedelta(days=LOOKAHEAD_DAYS)

    url = "https://api.football-data.org/v4/matches"
    data = _football_data_get(
        url,
        token,
        params={
            "dateFrom": date_from.strftime("%Y-%m-%d"),
            "dateTo": date_to.strftime("%Y-%m-%d"),
        },
    )

    matches = data.get("matches", []) or []

    # Filtra: solo SCHEDULED + competizioni allowlist + dentro fasce
    filtered = []
    for m in matches:
        if m.get("status") != "SCHEDULED":
            continue

        comp = m.get("competition") or {}
        comp_code = (comp.get("code") or "").strip()
        if comp_code and comp_code not in ALLOW_COMP_CODES:
            continue

        utc_dt = m.get("utcDate")
        if not utc_dt:
            continue

        try:
            dt_utc = datetime.fromisoformat(utc_dt.replace("Z", "+00:00"))
        except Exception:
            continue

        dt_rome = dt_utc.astimezone(TZ)
        slot = _slot_of(dt_rome)
        if not slot:
            continue

        home = m.get("homeTeam") or {}
        away = m.get("awayTeam") or {}

        match_id = int(m.get("id", 0)) or 0

        event = {
            "id": match_id,
            "slot": slot,
            "league": comp.get("name") or comp_code or "Calcio",
            "league_code": comp_code,
            "country": (comp.get("area") or {}).get("name", ""),
            "country_code": (comp.get("area") or {}).get("code", ""),
            "competition_emblem": comp.get("emblem", ""),
            "home": home.get("name") or "Home",
            "away": away.get("name") or "Away",
            "home_short": home.get("tla") or "",
            "away_short": away.get("tla") or "",
            "home_crest": home.get("crest") or "",
            "away_crest": away.get("crest") or "",
            "start_iso": dt_rome.isoformat(),
            "start": _format_start(dt_rome),
            # IMPORTANTISSIMO: qui NON inventiamo quote.
            "markets": [],
        }

        filtered.append((dt_rome, event))

    filtered.sort(key=lambda x: x[0])

    # Selezione 5/5/5 senza duplicati
    picked_ids = set()
    slots = {"mattina": [], "pomeriggio": [], "sera": []}

    for _, ev in filtered:
        if ev["id"] in picked_ids:
            continue
        s = ev["slot"]
        if len(slots[s]) >= PER_SLOT:
            continue
        slots[s].append(ev)
        picked_ids.add(ev["id"])

        if all(len(slots[k]) >= PER_SLOT for k in slots):
            break

    # Riempimento se mancano eventi in una fascia (sempre eventi REALI)
    if not all(len(slots[k]) >= PER_SLOT for k in slots):
        for _, ev in filtered:
            if ev["id"] in picked_ids:
                continue
            target = min(slots.keys(), key=lambda k: len(slots[k]))
            if len(slots[target]) >= PER_SLOT:
                break
            ev2 = dict(ev)
            ev2["slot"] = target
            slots[target].append(ev2)
            picked_ids.add(ev2["id"])
            if all(len(slots[k]) >= PER_SLOT for k in slots):
                break

    out_events = slots["mattina"] + slots["pomeriggio"] + slots["sera"]

    out = {
        "updated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "timezone": "Europe/Rome",
        "counts": {
            "mattina": len(slots["mattina"]),
            "pomeriggio": len(slots["pomeriggio"]),
            "sera": len(slots["sera"]),
            "total": len(out_events),
        },
        "events": out_events,
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_FILE} with {len(out_events)} events.")


if __name__ == "__main__":
    main()
