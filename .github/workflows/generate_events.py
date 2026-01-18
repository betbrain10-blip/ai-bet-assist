#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import math
import hashlib
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

# =========================
# CONFIG
# =========================
TZ_NAME = "Europe/Rome"
TZ = ZoneInfo(TZ_NAME)

# Campionati "primari" (Football-Data codes)
PRIMARY_COMPETITIONS = [
    ("PL",  "Premier League", "GB"),
    ("SA",  "Serie A",        "IT"),
    ("PD",  "LaLiga",         "ES"),
    ("BL1", "Bundesliga",     "DE"),
    ("FL1", "Ligue 1",        "FR"),
    ("CL",  "Champions League","EU"),
]

LOOKAHEAD_HOURS = 48  # quante ore avanti prendere (48 = 2 giorni, così trovi sempre match)

OUT_FILE = "events.json"
API_BASE = "https://api.football-data.org/v4"

# =========================
# UTILS
# =========================
def _stable_rand01(seed: str) -> float:
    """Numero pseudo-random deterministico 0..1 basato su seed."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # prendo 8 hex => int => 0..1
    x = int(h[:8], 16)
    return (x % 10_000_000) / 10_000_000.0

def _clamp(x, a, b):
    return max(a, min(b, x))

def _fmt_odd(x: float) -> float:
    return round(x + 1e-9, 2)

def _slot_for_local_hour(h: int) -> str:
    # mattina 06-12, pomeriggio 12-18, sera 18-24, notte 00-06
    if 6 <= h < 12:
        return "mattina"
    if 12 <= h < 18:
        return "pomeriggio"
    if 18 <= h < 24:
        return "sera"
    return "notte"

def _make_markets(match_seed: str):
    """
    Quote 'verosimili' (NON reali) ma stabili e vicine a range realistici.
    Il cliente poi può correggerle al banco.
    """
    r = _stable_rand01(match_seed)

    # 1X range ~ 1.25 - 1.75
    odd_1x = 1.25 + r * 0.50

    # Over 1.5 range ~ 1.25 - 1.65 (di solito più bassa)
    odd_o15 = 1.25 + (_stable_rand01(match_seed + "|o15")) * 0.40

    # Goal/NoGoal SI range ~ 1.45 - 2.05
    odd_gg = 1.45 + (_stable_rand01(match_seed + "|gg")) * 0.60

    return [
        {"label": "1X", "odd": _fmt_odd(_clamp(odd_1x, 1.20, 2.50))},
        {"label": "Over 1.5", "odd": _fmt_odd(_clamp(odd_o15, 1.15, 2.20))},
        {"label": "Goal/NoGoal Si", "odd": _fmt_odd(_clamp(odd_gg, 1.20, 3.50))},
    ]

def fetch_competition_matches(token: str, comp_code: str, date_from: str, date_to: str):
    url = f"{API_BASE}/competitions/{comp_code}/matches"
    params = {
        "status": "SCHEDULED",
        "dateFrom": date_from,
        "dateTo": date_to,
    }
    headers = {"X-Auth-Token": token}

    r = requests.get(url, params=params, headers=headers, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("RATE LIMIT (429): troppe richieste su Football-Data. Riprova più tardi o riduci la frequenza.")
    if r.status_code in (401, 403):
        raise RuntimeError(f"AUTH ERROR ({r.status_code}): token Football-Data mancante/sbagliato.")
    r.raise_for_status()

    data = r.json()
    return data.get("matches", [])

def main():
    token = os.getenv("FOOTBALL_DATA_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Manca la variabile FOOTBALL_DATA_TOKEN (imposta il Secret su GitHub).")

    now_utc = datetime.now(timezone.utc)
    end_utc = now_utc + timedelta(hours=LOOKAHEAD_HOURS)

    # Football-Data usa date (YYYY-MM-DD) non datetime, quindi allarghiamo al giorno intero
    date_from = now_utc.date().isoformat()
    date_to = end_utc.date().isoformat()

    events = []
    seen_keys = set()

    for comp_code, comp_name, country_code in PRIMARY_COMPETITIONS:
        try:
            matches = fetch_competition_matches(token, comp_code, date_from, date_to)
        except Exception as e:
            # Non blocchiamo tutto se un campionato fallisce (es. rate limit su uno)
            print(f"[WARN] {comp_code} -> {e}")
            continue

        for m in matches:
            # prendo solo quelli con data valida
            utc_date = m.get("utcDate")
            if not utc_date:
                continue

            # parse ISO
            try:
                dt_utc = datetime.fromisoformat(utc_date.replace("Z", "+00:00"))
            except Exception:
                continue

            # filtro: entro LOOKAHEAD_HOURS
            if dt_utc < now_utc or dt_utc > end_utc:
                continue

            home = (m.get("homeTeam") or {}).get("name") or "Home"
            away = (m.get("awayTeam") or {}).get("name") or "Away"

            # chiave univoca per evitare duplicati
            key = f"{comp_code}|{home}|{away}|{utc_date}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            dt_local = dt_utc.astimezone(TZ)
            start_local = dt_local.strftime("%d/%m %H:%M")
            slot = _slot_for_local_hour(dt_local.hour)

            match_id = str(m.get("id") or key)
            match_seed = f"{comp_code}|{match_id}|{utc_date}"

            event = {
                "id": match_id,
                "competition_code": comp_code,
                "league": comp_name,
                "country": country_code,          # per bandierina campionato (se la UI la usa)
                "home": home,
                "away": away,
                "utcDate": utc_date,
                "start_local": start_local,
                "slot": slot,                    # mattina/pomeriggio/sera/notte
                "markets": _make_markets(match_seed),
                "source": "football-data.org",
                "note": "Quote stimate e modificabili al banco"
            }
            events.append(event)

    # Ordina per orario
    def _sort_key(ev):
        try:
            return datetime.fromisoformat(ev["utcDate"].replace("Z", "+00:00"))
        except Exception:
            return datetime.max.replace(tzinfo=timezone.utc)

    events.sort(key=_sort_key)

    out = {
        "updated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "timezone": TZ_NAME,
        "range_hours": LOOKAHEAD_HOURS,
        "competitions": [c[0] for c in PRIMARY_COMPETITIONS],
        "events": events,
    }

    # Scrivi JSON sempre valido
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"[OK] Scritto {OUT_FILE} con {len(events)} eventi reali (primari).")

if __name__ == "__main__":
    main()
