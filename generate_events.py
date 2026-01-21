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

LOOKAHEAD_DAYS = 2          # oggi + prossimi 2 giorni
PER_SLOT = 5                # 5 mattina + 5 pomeriggio + 5 sera = 15

# Fasce orarie (Italia)
MORNING_START = 6
MORNING_END = 12
AFTERNOON_START = 12
AFTERNOON_END = 18
EVENING_START = 18
EVENING_END = 24

ALLOW_COMP_CODES = {
    "CL", "EL", "EC",
    "PL", "PD", "SA", "BL1", "FL1", "DED", "PPL",
}

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
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)

def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))

def _mk_strength(home: str, away: str, league_code: str) -> Tuple[float, float, float]:
    """
    Punteggi “pseudo” (0..1) per creare valutazioni coerenti, NON quote.
    Restituisce:
      - diff (home stronger positive)
      - tempo (ritmo) 0..1
      - goals (propensione goal) 0..1
    """
    key = f"{league_code}|{home}|{away}"
    x = _stable_int(key)

    home_s = ((x % 1000) / 1000.0)
    away_s = (((x // 1000) % 1000) / 1000.0)
    diff = _clamp(home_s - away_s, -0.8, 0.8)

    # ritmo e goal “pseudo” ma stabili
    tempo = ((x // 2000) % 1000) / 1000.0
    goals = ((x // 3000) % 1000) / 1000.0

    # leghe top un filo più “stabili”
    if league_code in {"PL","SA","PD","BL1","FL1"}:
        tempo = _clamp(tempo + 0.05, 0, 1)
    if league_code in {"CL","EL"}:
        tempo = _clamp(tempo - 0.03, 0, 1)

    return diff, tempo, goals

def _tag(score: float) -> str:
    if score >= 0.70: return "Alta"
    if score >= 0.50: return "Media"
    return "Bassa"

def _event_tip(diff: float, tempo: float, goals: float) -> str:
    # frase “cliente-friendly”
    if tempo > 0.68 and goals > 0.62:
        return "Ritmo alto e fase offensiva viva: partita da seguire con attenzione."
    if abs(diff) > 0.45:
        return "C’è una favorita abbastanza chiara: occhio alle giocate di copertura."
    if goals < 0.38:
        return "Possibile partita più bloccata: meglio scegliere con calma e verificare al banco."
    return "Match equilibrato: scegli 1 giocata sola e mantieni lo stake sotto controllo."

def _build_markets(home: str, away: str, league_code: str) -> List[Dict[str, Any]]:
    diff, tempo, goals = _mk_strength(home, away, league_code)

    # Score “valutazioni” (0..1), solo per tag/descrizione
    score_over25 = _clamp(0.35 + tempo*0.35 + goals*0.35, 0, 1)
    score_1x = _clamp(0.55 + (diff*0.35), 0, 1)
    score_gol = _clamp(0.40 + goals*0.40 + (0.20 - abs(diff)*0.15), 0, 1)

    markets = [
        {
            "label": "Over 2.5",
            "tag": _tag(score_over25),
            "note": "Attacchi attivi / ritmo gara: se vedi squadre che spingono, può avere senso."
        },
        {
            "label": "1X",
            "tag": _tag(score_1x),
            "note": "Copertura casa: utile se la squadra di casa sembra più solida o ha spinta del pubblico."
        },
        {
            "label": "Goal/NoGoal Sì",
            "tag": _tag(score_gol),
            "note": "Entrambe possono segnare: meglio se vedi difese distratte e occasioni da ambo i lati."
        },
    ]

    # Personalizza note in base ai punteggi
    for m in markets:
        if m["label"] == "Over 2.5":
            if score_over25 >= 0.70:
                m["note"] = "🔥 Alta spinta offensiva: partita da gol (verifica quota al banco)."
            elif score_over25 <= 0.45:
                m["note"] = "🧊 Potrebbe essere più chiusa: se non ti convince, salta e scegli altro."
        if m["label"] == "1X":
            if score_1x >= 0.72:
                m["note"] = "🛡️ Casa più affidabile: 1X da valutare come scelta “tranquilla”."
            elif score_1x <= 0.50:
                m["note"] = "⚠️ Equilibrio alto: 1X meno “sicuro”, valuta bene prima di aggiungere."
        if m["label"].startswith("Goal"):
            if score_gol >= 0.70:
                m["note"] = "⚡ Occasioni da entrambe: Goal Sì interessante, sempre con controllo stake."
            elif score_gol <= 0.50:
                m["note"] = "🔍 Non è detto che segnino entrambe: scegli solo se hai buone sensazioni."

    return markets

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

        diff, tempo, goals = _mk_strength(home_name, away_name, comp_code)
        tip = _event_tip(diff, tempo, goals)

        ev = {
            "id": match_id,
            "uniq": f"{match_id}|{utc_dt}|{home_name}|{away_name}",
            "slot": slot,
            "league": comp.get("name") or comp_code or "Calcio",
            "league_code": comp_code,
            "country": (comp.get("area") or {}).get("name", ""),
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
            "tip": tip,
            "markets": _build_markets(home_name, away_name, comp_code),
        }

        filtered.append((dt_rome, ev))

    filtered.sort(key=lambda x: x[0])

    picked_ids = set()
    slots: Dict[str, List[Dict[str, Any]]] = {"mattina": [], "pomeriggio": [], "sera": []}

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

    # riempi se manca una fascia
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

    print(f"Wrote {OUT_FILE} with {len(out_events)} events. counts={out['counts']}")

if __name__ == "__main__":
    main()
