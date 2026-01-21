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

LOOKAHEAD_DAYS = 2
PER_SLOT = 5

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

def _mk_strength(home: str, away: str, league_code: str) -> Tuple[float, float, float, float]:
    """
    diff: >0 home più forte, <0 away più forte
    tempo: ritmo/pressione
    goals: propensione ai gol
    grit: "agonismo"/fisicità (per cartellini)
    """
    key = f"{league_code}|{home}|{away}"
    x = _stable_int(key)

    home_s = ((x % 1000) / 1000.0)
    away_s = (((x // 1000) % 1000) / 1000.0)
    diff = _clamp(home_s - away_s, -0.9, 0.9)

    tempo = ((x // 2000) % 1000) / 1000.0
    goals = ((x // 3000) % 1000) / 1000.0
    grit = ((x // 4000) % 1000) / 1000.0

    # Leghe top: un filo più "ordinate"
    if league_code in {"PL","SA","PD","BL1","FL1"}:
        tempo = _clamp(tempo + 0.05, 0, 1)

    # Coppe: spesso più tattiche
    if league_code in {"CL","EL"}:
        tempo = _clamp(tempo - 0.03, 0, 1)
        grit = _clamp(grit + 0.05, 0, 1)

    return diff, tempo, goals, grit

def _tag(score: float) -> str:
    if score >= 0.74: return "Alta"
    if score >= 0.54: return "Media"
    return "Bassa"

def _fav_label(diff: float) -> str:
    if diff >= 0.28: return "home"
    if diff <= -0.28: return "away"
    return "balanced"

def _event_tip(diff: float, tempo: float, goals: float) -> str:
    fav = _fav_label(diff)
    if fav == "home":
        if tempo > 0.62:
            return "Casa favorita con ritmo buono: se scegli, mantieni poche selezioni."
        return "Casa favorita: ok coperture, ma verifica sempre la quota al banco."
    if fav == "away":
        if tempo > 0.62:
            return "Ospiti favoriti: attenzione alle giocate “comode”, spesso quota bassa."
        return "Favorita esterna: 1X rischiosa. Meglio prudenza."
    if goals > 0.65 and tempo > 0.60:
        return "Equilibrio ma partita viva: può diventare aperta, scegli con testa."
    if goals < 0.40:
        return "Possibile gara bloccata: se non ti convince, salta."
    return "Match equilibrato: una sola giocata fatta bene vale di più."

def _build_markets_and_scores(home: str, away: str, league_code: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    diff, tempo, goals, grit = _mk_strength(home, away, league_code)
    fav = _fav_label(diff)

    # Score "indicativi"
    score_over25 = _clamp(0.25 + tempo*0.40 + goals*0.45, 0, 1)
    score_goal = _clamp(0.25 + goals*0.55 + (0.25 - abs(diff)*0.20), 0, 1)

    # 1X realistico
    if fav == "home":
        score_1x = _clamp(0.70 + diff*0.20, 0, 1)
    elif fav == "balanced":
        score_1x = _clamp(0.55 + diff*0.12, 0, 1)
    else:
        score_1x = _clamp(0.40 + (diff+0.28)*0.10, 0, 1)

    # Corner: più ritmo/pressione => più corner
    score_corners = _clamp(0.22 + tempo*0.62 + goals*0.18 - abs(diff)*0.08, 0, 1)

    # Cartellini: più agonismo + equilibrio/pressione => più cartellini
    score_cards = _clamp(0.20 + grit*0.55 + abs(diff)*0.18 + (0.25 - goals*0.18), 0, 1)

    # Note
    note_over = "Ritmo e occasioni: se vedi squadre che spingono, può avere senso (quota al banco)."
    if score_over25 >= 0.78:
        note_over = "🔥 Gara da gol probabile: ritmo alto e occasioni. Stake controllato."
    elif score_over25 <= 0.45:
        note_over = "🧊 Rischio gara chiusa: se sei indeciso, meglio saltare."

    if fav == "home":
        note_1x = "🛡️ Casa favorita: 1X può essere copertura sensata (verifica quota)."
        if score_1x < 0.55:
            note_1x = "⚠️ Casa favorita ma non troppo: 1X ok solo se ti convince."
    elif fav == "balanced":
        note_1x = "⚖️ Equilibrio: 1X discreta ma non “sicura”. Verifica quota."
        if score_1x < 0.52:
            note_1x = "⚠️ Equilibrio forte: 1X non è facile. Meglio una sola selezione."
    else:
        note_1x = "🚨 Ospiti favoriti: 1X rischiosa. Valutala solo con motivo chiaro."

    note_goal = "Entrambe possono segnare: meglio se vedi occasioni da entrambe."
    if score_goal >= 0.76:
        note_goal = "⚡ Buone chance Goal Sì: potenziale da entrambe. Stake controllato."
    elif score_goal <= 0.50:
        note_goal = "🔍 Goal Sì non scontato: scegli solo se ti convince."

    markets = [
        {"label": "Over 2.5", "tag": _tag(score_over25), "note": note_over},
        {"label": "1X", "tag": _tag(score_1x), "note": note_1x},
        {"label": "Goal/NoGoal Sì", "tag": _tag(score_goal), "note": note_goal},
    ]

    scores = {
        "diff": float(f"{diff:.2f}"),
        "fav": fav,
        "tempo": float(f"{tempo:.2f}"),
        "goals": float(f"{goals:.2f}"),
        "grit": float(f"{grit:.2f}"),
        "corners": float(f"{score_corners:.2f}"),
        "cards": float(f"{score_cards:.2f}"),
    }
    return markets, scores

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

        markets, ctx = _build_markets_and_scores(home_name, away_name, comp_code)
        tip = _event_tip(ctx["diff"], ctx["tempo"], ctx["goals"])

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
            "context": ctx,          # <-- QUI CI SONO corners/cards
            "markets": markets,
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
