import os
import json
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

# Aumentiamo la finestra: più probabilità di trovare eventi reali
LOOKAHEAD_DAYS = 7

OUT_FILE = "events.json"

# Competizioni "primarie" (se il piano non le include, Football-Data risponde comunque con i match
# ma noi non le blocchiamo: se manca il code, le accettiamo lo stesso)
ALLOW_COMP_CODES = {
    "CL", "EL",
    "PL", "PD", "SA", "BL1", "FL1",
    "DED", "PPL",
    "EC", "WC",
    "BSA",
    "SB",   # se inclusa
    "CH",   # se inclusa
    "MLS",  # se inclusa
}

# Status reali di Football-Data per partite non iniziate
ALLOWED_STATUS = {"SCHEDULED", "TIMED"}


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
    now = datetime.now(TZ)
    if dt_rome.date() == now.date():
        day = "Oggi"
    elif dt_rome.date() == (now.date() + timedelta(days=1)):
        day = "Domani"
    else:
        wk = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
        day = wk[dt_rome.weekday()]
    return f"{day} {dt_rome.strftime('%H:%M')}"


def _slot_of(dt_rome: datetime) -> str:
    # Se fuori fascia (notte), la mettiamo in "sera" così non perdiamo eventi reali
    h = dt_rome.hour
    if MORNING_START <= h < MORNING_END:
        return "mattina"
    if AFTERNOON_START <= h < AFTERNOON_END:
        return "pomeriggio"
    if EVENING_START <= h < EVENING_END:
        return "sera"
    return "sera"


def _stable_rng(seed_value: int) -> random.Random:
    rng = random.Random()
    rng.seed(seed_value)
    return rng


def _mk_odds(match_seed: int, market_type: str) -> float:
    """
    Quote NON reali del book (Football-Data non fornisce quote).
    Sono "stabili" (non cambiano a ogni refresh) per lo stesso match.
    """
    rng = _stable_rng(match_seed * 97 + sum(ord(c) for c in market_type))

    if market_type == "over15":
        v = rng.uniform(1.35, 1.70)
    elif market_type == "over25":
        v = rng.uniform(1.55, 2.10)
    elif market_type == "goal_si":
        v = rng.uniform(1.55, 2.05)
    elif market_type == "1x":
        v = rng.uniform(1.25, 1.75)
    elif market_type == "dnb1":
        v = rng.uniform(1.40, 2.10)
    else:
        v = rng.uniform(1.50, 2.20)

    return float(f"{v:.2f}")


def _build_markets(match_seed: int) -> list[dict]:
    return [
        {"label": "Over 1.5", "odd": _mk_odds(match_seed, "over15")},
        {"label": "1X", "odd": _mk_odds(match_seed, "1x")},
        {"label": "Goal/NoGoal Sì", "odd": _mk_odds(match_seed, "goal_si")},
    ]


def _date_str(d) -> str:
    return d.strftime("%Y-%m-%d")


def main():
    token = _env_token()

    today = datetime.now(TZ).date()
    date_from = today
    date_to = today + timedelta(days=LOOKAHEAD_DAYS)

    url = "https://api.football-data.org/v4/matches"
    data = _football_data_get(
        url,
        token,
        params={"dateFrom": _date_str(date_from), "dateTo": _date_str(date_to)},
    )

    matches = data.get("matches", []) or []

    filtered = []
    for m in matches:
        status = (m.get("status") or "").strip()
        if status not in ALLOWED_STATUS:
            continue

        comp = m.get("competition") or {}
        comp_code = (comp.get("code") or "").strip()

        # Se comp_code esiste e NON è tra le primarie -> scartiamo.
        # Se comp_code manca (piani limitati / alcune competizioni), lo accettiamo comunque.
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

        home = (m.get("homeTeam") or {})
        away = (m.get("awayTeam") or {})

        match_id = int(m.get("id") or 0)

        # Chiave univoca anti-duplicati
        uniq_key = f"{match_id}|{utc_dt}|{home.get('name','')}|{away.get('name','')}"

        # Seed stabile per quote "verosimili"
        seed = match_id if match_id else abs(hash(uniq_key)) % 10**9

        event = {
            "id": match_id or seed,
            "uniq": uniq_key,
            "slot": slot,  # mattina/pomeriggio/sera
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
            "markets": _build_markets(seed),
        }

        filtered.append((dt_rome, event))

    filtered.sort(key=lambda x: x[0])

    picked = set()
    slots = {"mattina": [], "pomeriggio": [], "sera": []}

    # 1) Prendi 5 per fascia se disponibili
    for _, ev in filtered:
        if ev["uniq"] in picked:
            continue
        s = ev["slot"]
        if len(slots[s]) >= PER_SLOT:
            continue
        slots[s].append(ev)
        picked.add(ev["uniq"])

        if all(len(slots[k]) >= PER_SLOT for k in slots):
            break

    # 2) Se manca qualche fascia, riempi con altri eventi reali (forzando la fascia più vuota)
    if not all(len(slots[k]) >= PER_SLOT for k in slots):
        for _, ev in filtered:
            if ev["uniq"] in picked:
                continue
            target = min(slots.keys(), key=lambda k: len(slots[k]))
            if len(slots[target]) >= PER_SLOT:
                break
            ev2 = dict(ev)
            ev2["slot"] = target
            slots[target].append(ev2)
            picked.add(ev2["uniq"])
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

    # Scrive SEMPRE JSON valido
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUT_FILE} with {len(out_events)} events.")


if __name__ == "__main__":
    main()
