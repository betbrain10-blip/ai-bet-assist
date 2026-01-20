import os
import json
import math
import random
import time
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

# Competizioni principali (Football-Data codes)
ALLOW_COMP_CODES = {
    "CL", "EL", "EC",
    "PL", "PD", "SA", "BL1", "FL1",
    "DED", "PPL",
}

LOOKAHEAD_DAYS = 2
OUT_FILE = "events.json"

# Quante partite passate usare per stimare i gol (per team)
FORM_MATCHES = 6

# Margine bookmaker (più alto = quote più basse)
BOOK_MARGIN = 0.06  # 6%

# Limiti quote (evita roba assurda)
MIN_ODD = 1.15
MAX_ODD = 5.50

# Rate limit “gentile” verso Football-Data
SLEEP_BETWEEN_CALLS = 0.25

BASE_URL = "https://api.football-data.org/v4"


# =========================
# FOOTBALL-DATA API
# =========================
def _env_token() -> str:
    t = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not t:
        raise RuntimeError("FOOTBALL_DATA_TOKEN missing in env (GitHub Secrets).")
    return t


def _fd_get(path: str, token: str, params: dict | None = None) -> dict:
    headers = {"X-Auth-Token": token}
    url = f"{BASE_URL}{path}"
    r = requests.get(url, headers=headers, params=params, timeout=30)
    r.raise_for_status()
    time.sleep(SLEEP_BETWEEN_CALLS)
    return r.json()


# =========================
# TIME / SLOT
# =========================
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


def _iso_date(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")


# =========================
# MATH: Poisson + mercati
# =========================
def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _prob_match_outcomes(lam_home: float, lam_away: float, max_goals: int = 10) -> tuple[float, float, float]:
    """
    Ritorna (P_home_win, P_draw, P_away_win) via enumerazione Poisson fino a max_goals.
    """
    ph = [ _poisson_pmf(i, lam_home) for i in range(max_goals + 1) ]
    pa = [ _poisson_pmf(i, lam_away) for i in range(max_goals + 1) ]

    p_hw = 0.0
    p_d = 0.0
    p_aw = 0.0

    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_hw += p
            elif i == j:
                p_d += p
            else:
                p_aw += p

    # massa persa oltre max_goals: normalizziamo leggermente
    tot = p_hw + p_d + p_aw
    if tot > 0:
        p_hw /= tot
        p_d  /= tot
        p_aw /= tot

    return p_hw, p_d, p_aw


def _odd_from_prob(p: float, margin: float = BOOK_MARGIN) -> float:
    """
    Trasforma prob in quota “book” con margine.
    quota = 1 / (p * (1 - margin))
    """
    p = _clamp(p, 1e-6, 0.999999)
    o = 1.0 / (p * (1.0 - margin))
    o = _clamp(o, MIN_ODD, MAX_ODD)
    return float(f"{o:.2f}")


# =========================
# TEAM FORM (ultime partite finite)
# =========================
def _team_form_stats(team_id: int, token: str, cache: dict) -> dict:
    """
    Ritorna medie gol fatti/subiti nelle ultime FORM_MATCHES partite finite.
    Cache per evitare troppe chiamate.
    """
    if team_id in cache:
        return cache[team_id]

    try:
        data = _fd_get(
            f"/teams/{team_id}/matches",
            token,
            params={"status": "FINISHED", "limit": FORM_MATCHES}
        )
        matches = data.get("matches") or []
    except Exception:
        cache[team_id] = {"gf": 1.25, "ga": 1.25, "n": 0}
        return cache[team_id]

    gf = 0.0
    ga = 0.0
    n = 0

    for m in matches:
        score = (m.get("score") or {}).get("fullTime") or {}
        hg = score.get("home")
        ag = score.get("away")
        if hg is None or ag is None:
            continue

        home = (m.get("homeTeam") or {}).get("id")
        away = (m.get("awayTeam") or {}).get("id")
        if home is None or away is None:
            continue

        if team_id == home:
            gf += float(hg)
            ga += float(ag)
            n += 1
        elif team_id == away:
            gf += float(ag)
            ga += float(hg)
            n += 1

    if n <= 0:
        # fallback neutro
        res = {"gf": 1.25, "ga": 1.25, "n": 0}
    else:
        res = {"gf": gf / n, "ga": ga / n, "n": n}

    cache[team_id] = res
    return res


def _estimate_lambdas(home_id: int, away_id: int, token: str, cache: dict) -> tuple[float, float]:
    """
    Stima gol attesi (lambda) da forma recente.
    Aggiunge piccolo vantaggio casa.
    """
    hs = _team_form_stats(home_id, token, cache)
    as_ = _team_form_stats(away_id, token, cache)

    # Attacco vs difesa (media semplice)
    lam_home = (hs["gf"] + as_["ga"]) / 2.0
    lam_away = (as_["gf"] + hs["ga"]) / 2.0

    # Home advantage leggero
    lam_home *= 1.08

    # clamp ragionevoli
    lam_home = _clamp(lam_home, 0.55, 2.60)
    lam_away = _clamp(lam_away, 0.55, 2.40)

    return lam_home, lam_away


# =========================
# FALLBACK STABILE (se manca forma)
# =========================
def _stable_rng(seed_value: int) -> random.Random:
    rng = random.Random()
    rng.seed(seed_value)
    return rng


def _fallback_odds(match_id: int, market_type: str) -> float:
    rng = _stable_rng(match_id * 97 + sum(ord(c) for c in market_type))
    if market_type == "over15":
        v = rng.uniform(1.35, 1.75)
    elif market_type == "1x":
        v = rng.uniform(1.25, 1.80)
    elif market_type == "btts":
        v = rng.uniform(1.55, 2.10)
    else:
        v = rng.uniform(1.50, 2.20)
    return float(f"{v:.2f}")


def _build_markets_realistic(match_id: int, lam_home: float | None, lam_away: float | None) -> list[dict]:
    """
    Mercati:
    - Over 1.5 (totale)
    - 1X (home win o draw)
    - Goal/NoGoal Sì (BTTS)
    """
    if lam_home is None or lam_away is None:
        return [
            {"label": "Over 1.5", "odd": _fallback_odds(match_id, "over15")},
            {"label": "1X", "odd": _fallback_odds(match_id, "1x")},
            {"label": "Goal/NoGoal Sì", "odd": _fallback_odds(match_id, "btts")},
        ]

    # Totale gol ~ Poisson(lam_home + lam_away)
    lam_total = lam_home + lam_away

    # P(Over 1.5) = 1 - P(0) - P(1)
    p0 = _poisson_pmf(0, lam_total)
    p1 = _poisson_pmf(1, lam_total)
    p_over15 = _clamp(1.0 - (p0 + p1), 0.01, 0.99)

    # BTTS (Goal Sì) = 1 - P(H=0) - P(A=0) + P(H=0,A=0)
    p_h0 = _poisson_pmf(0, lam_home)
    p_a0 = _poisson_pmf(0, lam_away)
    p_both0 = p_h0 * p_a0
    p_btts = _clamp(1.0 - p_h0 - p_a0 + p_both0, 0.01, 0.99)

    # 1X = P(home win) + P(draw)
    p_hw, p_d, _ = _prob_match_outcomes(lam_home, lam_away, max_goals=10)
    p_1x = _clamp(p_hw + p_d, 0.01, 0.99)

    return [
        {"label": "Over 1.5", "odd": _odd_from_prob(p_over15)},
        {"label": "1X", "odd": _odd_from_prob(p_1x)},
        {"label": "Goal/NoGoal Sì", "odd": _odd_from_prob(p_btts)},
    ]


# =========================
# MAIN
# =========================
def main():
    token = _env_token()
    today = datetime.now(TZ).date()
    date_from = today
    date_to = today + timedelta(days=LOOKAHEAD_DAYS)

    # 1) Prende match in range
    data = _fd_get(
        "/matches",
        token,
        params={
            "dateFrom": _iso_date(datetime.combine(date_from, datetime.min.time())),
            "dateTo": _iso_date(datetime.combine(date_to, datetime.min.time())),
        },
    )
    matches = data.get("matches", []) or []

    # cache per forma team
    form_cache: dict[int, dict] = {}

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

        home = (m.get("homeTeam") or {})
        away = (m.get("awayTeam") or {})
        home_id = home.get("id")
        away_id = away.get("id")

        match_id = int(m.get("id", 0)) or int(abs(hash(f"{home.get('name')}|{away.get('name')}|{utc_dt}")) % 10**9)

        # 2) Stima lambdas da forma recente
        lam_home = None
        lam_away = None
        if isinstance(home_id, int) and isinstance(away_id, int):
            try:
                lam_home, lam_away = _estimate_lambdas(home_id, away_id, token, form_cache)
            except Exception:
                lam_home, lam_away = None, None

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
            "markets": _build_markets_realistic(match_id, lam_home, lam_away),
        }

        filtered.append((dt_rome, event))

    # Ordina per orario
    filtered.sort(key=lambda x: x[0])

    # 3) Pick 5/5/5
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

    # Se qualche fascia è vuota, riempi “forzando” lo slot (evento reale)
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
