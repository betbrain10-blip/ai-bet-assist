import os
import json
import math
import random
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
# (Se il tuo piano non le include tutte, verranno semplicemente ignorate)
ALLOW_COMP_CODES = {
    "CL",   # Champions League
    "EL",   # Europa League
    "EC",   # Conference League (in alcuni piani può variare, se non esce non succede nulla)
    "PL",   # Premier League
    "PD",   # LaLiga
    "SA",   # Serie A
    "BL1",  # Bundesliga
    "FL1",  # Ligue 1
    "DED",  # Eredivisie
    "PPL",  # Primeira Liga
}

# Quanto avanti cercare partite
LOOKAHEAD_DAYS = 2

OUT_FILE = "events.json"


def _env_token() -> str:
    t = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN missing in env (GitHub Secrets).")
    return t


def _football_data_get(url: str, token: str, params: dict | None = None) -> dict:
    headers = {"X-Auth-Token": token}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _format_start(dt_rome: datetime) -> str:
    # Esempio: "Oggi 20:45" oppure "Dom 14:00"
    now = datetime.now(TZ)
    if dt_rome.date() == now.date():
        day = "Oggi"
    elif dt_rome.date() == (now.date() + timedelta(days=1)):
        day = "Domani"
    else:
        # Giorni abbreviati in IT
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


def _stable_rng(seed_value: int) -> random.Random:
    rng = random.Random()
    rng.seed(seed_value)
    return rng


def _mk_odds(match_id: int, market_type: str) -> float:
    """
    Quote "verosimili" (non quote reali del book).
    Stabili: a parità di match_id non cambiano a ogni refresh.
    """
    rng = _stable_rng(match_id * 97 + sum(ord(c) for c in market_type))

    # range tipici
    if market_type == "over15":
        v = rng.uniform(1.35, 1.70)
    elif market_type == "over25":
        v = rng.uniform(1.55, 2.05)
    elif market_type == "goal_si":
        v = rng.uniform(1.55, 2.00)
    elif market_type == "1x":
        v = rng.uniform(1.25, 1.70)
    elif market_type == "dnb1":
        v = rng.uniform(1.40, 2.05)
    else:
        v = rng.uniform(1.50, 2.10)

    # arrotonda a 2 decimali
    return float(f"{v:.2f}")


def _build_markets(match_id: int) -> list[dict]:
    # Misti (semplici e “da banco”)
    return [
        {"label": "Over 1.5", "odd": _mk_odds(match_id, "over15")},
        {"label": "1X", "odd": _mk_odds(match_id, "1x")},
        {"label": "Goal/NoGoal Sì", "odd": _mk_odds(match_id, "goal_si")},
    ]


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def main():
    token = _env_token()

    today = datetime.now(TZ).date()
    date_from = today
    date_to = today + timedelta(days=LOOKAHEAD_DAYS)

    # endpoint generale match (più semplice, poi filtriamo per competizione)
    url = "https://api.football-data.org/v4/matches"
    data = _football_data_get(
        url,
        token,
        params={
            "dateFrom": _iso_date(datetime.combine(date_from, datetime.min.time())),
            "dateTo": _iso_date(datetime.combine(date_to, datetime.min.time())),
        },
    )

    matches = data.get("matches", []) or []

    # Filtra: solo SCHEDULED + competizioni in allowlist
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

        # parse ISO: "2026-01-17T20:45:00Z"
        try:
            dt_utc = datetime.fromisoformat(utc_dt.replace("Z", "+00:00"))
        except Exception:
            continue

        dt_rome = dt_utc.astimezone(TZ)
        slot = _slot_of(dt_rome)
        if not slot:
            # fuori fasce (es. notte) → ignoriamo
            continue

        home = (m.get("homeTeam") or {})
        away = (m.get("awayTeam") or {})

        match_id = int(m.get("id", 0)) or int(abs(hash(f"{home.get('name')}|{away.get('name')}|{utc_dt}")) % 10**9)

        event = {
            "id": match_id,
            "slot": slot,  # "mattina" / "pomeriggio" / "sera"
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
            "markets": _build_markets(match_id),
        }

        filtered.append((dt_rome, event))

    # Ordina per orario
    filtered.sort(key=lambda x: x[0])

    # Selezione 5/5/5 senza duplicati (id univoco)
    picked_ids = set()
    slots = {"mattina": [], "pomeriggio": [], "sera": []}

    for dt_rome, ev in filtered:
        if ev["id"] in picked_ids:
            continue
        s = ev["slot"]
        if len(slots[s]) >= PER_SLOT:
            continue
        slots[s].append(ev)
        picked_ids.add(ev["id"])

        if all(len(slots[k]) >= PER_SLOT for k in slots):
            break

    # Se una fascia ha meno di 5 (manca copertura), riempiamo con altri eventi restanti (sempre reali),
    # mantenendo comunque 15 totali se possibile.
    if not all(len(slots[k]) >= PER_SLOT for k in slots):
        for dt_rome, ev in filtered:
            if ev["id"] in picked_ids:
                continue

            # trova fascia più “vuota”
            target = min(slots.keys(), key=lambda k: len(slots[k]))
            if len(slots[target]) >= PER_SLOT:
                break

            # forziamo lo slot target solo per riempire la schermata (evento sempre reale)
            ev2 = dict(ev)
            ev2["slot"] = target
            slots[target].append(ev2)
            picked_ids.add(ev2["id"])

            if all(len(slots[k]) >= PER_SLOT for k in slots):
                break

    # Output finale: concateno in ordine mattina->pomeriggio->sera
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

    # Scrive JSON valido SEMPRE
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_FILE} with {len(out_events)} events.")


if __name__ == "__main__":
    main()
