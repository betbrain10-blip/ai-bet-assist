import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional, Tuple
import hashlib

import requests


# =========================
# CONFIG
# =========================
TZ = ZoneInfo("Europe/Rome")
OUT_FILE = "events.json"

LOOKAHEAD_DAYS = 2          # cerca partite oggi + prossimi 2 giorni
PER_SLOT = 5                # 5 mattina + 5 pomeriggio + 5 sera = 15

# Fasce orarie (Italia)
MORNING_START = 6
MORNING_END = 12
AFTERNOON_START = 12
AFTERNOON_END = 18
EVENING_START = 18
EVENING_END = 24

# Competizioni principali europee (Football-Data codes)
ALLOW_COMP_CODES = {
    "CL",   # Champions League
    "EL",   # Europa League
    "EC",   # Conference League (se il piano la supporta)
    "PL",   # Premier League
    "PD",   # LaLiga
    "SA",   # Serie A
    "BL1",  # Bundesliga
    "FL1",  # Ligue 1
    "DED",  # Eredivisie
    "PPL",  # Primeira Liga
}

# Margine “book” per rendere le quote più realistiche (più basso = quote più alte)
BOOK_MARGIN = 0.06


# =========================
# HELPERS
# =========================
def _env_token() -> str:
    t = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN missing in env (GitHub Secrets).")
    return t


def _get_json(url: str, token: str, params: Optional[dict] = None) -> dict:
    headers = {"X-Auth-Token": token}
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


def _slot_of(dt_rome: datetime) -> Optional[str]:
    h = dt_rome.hour
    if MORNING_START <= h < MORNING_END:
        return "mattina"
    if AFTERNOON_START <= h < AFTERNOON_END:
        return "pomeriggio"
    if EVENING_START <= h < EVENING_END:
        return "sera"
    return None


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


def _stable_int(s: str) -> int:
    # numero stabile 0..2^31-1 dalla stringa (per avere quote stabili a parità match)
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


def _odd_from_prob(p: float, margin: float = BOOK_MARGIN) -> float:
    # quota “da book”: più bassa della fair
    p = _clamp(p, 0.02, 0.98)
    fair = 1.0 / p
    book = fair * (1.0 - margin)
    return float(f"{book:.2f}")


def _mk_probs(home: str, away: str, league_code: str) -> Tuple[float, float, float]:
    """
    Genera probabilità REALISTICHE (non casuali pure) basate su:
    - forza relativa (hash dei nomi)
    - competizione (leghe top un po' più "stabili")
    Restituisce: (p_over25, p_1x, p_goal_si)
    """
    key = f"{league_code}|{home}|{away}"
    x = _stable_int(key)

    # forza “pseudo” 0..1
    home_s = ((x % 1000) / 1000.0)
    away_s = (((x // 1000) % 1000) / 1000.0)
    diff = home_s - away_s  # positivo = home più forte

    # base per leghe
    league_bias = 0.0
    if league_code in {"PL", "SA", "PD", "BL1", "FL1"}:
        league_bias = 0.02
    if league_code in {"CL", "EL"}:
        league_bias = -0.01  # spesso match più “tattici”

    # Over 2.5: 0.40 - 0.70
    p_over25 = 0.52 + (diff * 0.08) + league_bias
    p_over25 = _clamp(p_over25, 0.40, 0.70)

    # Goal Sì: 0.45 - 0.65
    p_goal_si = 0.54 + (abs(diff) * -0.05) + (league_bias * 0.5)
    p_goal_si = _clamp(p_goal_si, 0.45, 0.65)

    # 1X: 0.58 - 0.82 (dipende molto dalla forza home)
    p_1x = 0.70 + (diff * 0.18)
    p_1x = _clamp(p_1x, 0.58, 0.82)

    return p_over25, p_1x, p_goal_si


def _build_markets(home: str, away: str, league_code: str) -> List[Dict[str, Any]]:
    p_over25, p_1x, p_goal_si = _mk_probs(home, away, league_code)

    odd_over25 = _odd_from_prob(p_over25)
    odd_1x = _odd_from_prob(p_1x)
    odd_goal_si = _odd_from_prob(p_goal_si)

    # Clamp finale in range “credibili” (per evitare estremi strani)
    odd_over25 = float(f"{_clamp(odd_over25, 1.45, 2.20):.2f}")
    odd_1x = float(f"{_clamp(odd_1x, 1.25, 1.80):.2f}")
    odd_goal_si = float(f"{_clamp(odd_goal_si, 1.50, 2.05):.2f}")

    return [
        {"label": "Over 2.5", "odd": odd_over25},
        {"label": "1X", "odd": odd_1x},
        {"label": "Goal/NoGoal Sì", "odd": odd_goal_si},
    ]


def main():
    token = _env_token()

    today = datetime.now(TZ).date()
    date_from = today
    date_to = today + timedelta(days=LOOKAHEAD_DAYS)

    url = "https://api.football-data.org/v4/matches"
    data = _get_json(
        url,
        token,
        params={
            "dateFrom": _iso_date(datetime.combine(date_from, datetime.min.time())),
            "dateTo": _iso_date(datetime.combine(date_to, datetime.min.time())),
        },
    )

    matches = data.get("matches", []) or []
    filtered: List[Tuple[datetime, Dict[str, Any]]] = []

    for m in matches:
        # Prendiamo scheduled e, se ci sono, anche TIMED (alcuni piani/status)
        status = (m.get("status") or "").upper()
        if status not in {"SCHEDULED", "TIMED"}:
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

        home = (m.get("homeTeam") or {})
        away = (m.get("awayTeam") or {})
        home_name = home.get("name") or "Home"
        away_name = away.get("name") or "Away"

        match_id = int(m.get("id", 0)) or _stable_int(f"{home_name}|{away_name}|{utc_dt}")

        ev = {
            "id": match_id,
            "uniq": f"{match_id}|{utc_dt}|{home_name}|{away_name}",
            "slot": slot,
            "league": comp.get("name") or comp_code or "Calcio",
            "league_code": comp_code,
            "country": (comp.get("area") or {}).get("code", "") or (comp.get("area") or {}).get("name", ""),
            "country_code": (comp.get("area") or {}).get("code", ""),
            "competition_emblem": comp.get("emblem", ""),
            "home": home_name,
            "away": away_name,
            "home_short": home.get("tla") or "",
            "away_short": away.get("tla") or "",
            "home_crest": home.get("crest") or "",
            "away_crest": away.get("crest") or "",
            "start_iso": dt_rome.isoformat(),
            "start": _format_start(dt_rome),
            "markets": _build_markets(home_name, away_name, comp_code),
        }

        filtered.append((dt_rome, ev))

    filtered.sort(key=lambda x: x[0])

    # Prendiamo 5 per slot (mattina/pomeriggio/sera)
    picked_ids = set()
    slots: Dict[str, List[Dict[str, Any]]] = {"mattina": [], "pomeriggio": [], "sera": []}

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

    # Se manca copertura in qualche fascia, riempiamo con eventi reali rimasti
    if not all(len(slots[k]) >= PER_SLOT for k in slots):
        for dt_rome, ev in filtered:
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

    print(f"Wrote {OUT_FILE} with {len(out_events)} events. counts={out['counts']}")


if __name__ == "__main__":
    main()
