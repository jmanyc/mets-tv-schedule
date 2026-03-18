#!/usr/bin/env python3
"""
Generate a Mets 2026 iCal (.ics) file from the broadcast schedule JSON.

Data source priority:
  1. MLB Stats API data (when SNY listings are available)
  2. Manually-parsed broadcast schedule (fallback)
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA_DIR = Path(__file__).parent.parent / "data"
DOCS_DIR = Path(__file__).parent.parent / "docs"
MANUAL_JSON = DATA_DIR / "mets_broadcast_schedule_full.json"
API_JSON = DATA_DIR / "mlb_api_schedule.json"  # written by fetch_mlb_api.py if available
OUTPUT_ICS = DOCS_DIR / "mets_2026.ics"

ET = ZoneInfo("America/New_York")
GAME_DURATION = timedelta(hours=3, minutes=30)

NETWORK_NOTES = {
    "SNY":        "SNY (cable)",
    "PIX11":      "PIX11 (free OTA, ch.11)",
    "FOX":        "FOX (free OTA)",
    "ESPN":       "ESPN (cable)",
    "NBC/Peacock":"NBC / Peacock",
    "NBC":        "NBC (free OTA) / Peacock",
    "Peacock":    "Peacock (streaming)",
    "Apple TV+":  "Apple TV+ (streaming)",
    "FS1":        "FS1 (cable)",
    "TBS":        "TBS (cable)",
    "MLB Network":"MLB Network (cable)",
}

def load_manual_data():
    with open(MANUAL_JSON) as f:
        return json.load(f)

def load_api_overrides():
    """
    Load MLB API data and extract games that have meaningful TV broadcast info.
    Returns a dict keyed by date string (YYYY-MM-DD) with broadcast details.
    """
    if not API_JSON.exists():
        return {}

    with open(API_JSON) as f:
        api_data = json.load(f)

    overrides = {}
    for date_entry in api_data.get("dates", []):
        for game in date_entry.get("games", []):
            date = game.get("officialDate")
            tv_broadcasts = [
                b for b in game.get("broadcasts", [])
                if b.get("type") == "TV"
            ]
            # Only override if there's actual TV data beyond opponent team feeds
            mets_relevant = [
                b for b in tv_broadcasts
                if b.get("availability", {}).get("availabilityCode") in ("national", "exclusive")
                or b.get("name") in ("SNY", "PIX11")
            ]
            if mets_relevant:
                overrides[date] = {
                    "networks": list({b["name"] for b in mets_relevant}),
                    "gameDate": game.get("gameDate"),
                }
    return overrides

def parse_time(date_str, time_str):
    """Parse '2026-04-01' + '7:10 PM' into a timezone-aware datetime."""
    dt_str = f"{date_str} {time_str}"
    naive = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
    return naive.replace(tzinfo=ET)

def fmt_dt(dt):
    """Format datetime for iCal (with timezone)."""
    return dt.strftime("%Y%m%dT%H%M%S")

def network_label(network):
    return NETWORK_NOTES.get(network, network)

def make_summary(entry, api_override=None):
    network = api_override["networks"][0] if api_override else entry.get("network", "")
    opponent = entry["opponent"]
    home_away = entry.get("home_away")
    if home_away == "home":
        matchup = f"Mets vs {opponent}"
    else:
        matchup = f"Mets @ {opponent}"
    return f"{matchup} [{network}]"

def make_description(entry, api_override=None):
    lines = []

    home_away = entry.get("home_away")
    opponent = entry["opponent"]
    if home_away == "home":
        lines.append(f"Home: New York Mets vs {opponent}")
    else:
        lines.append(f"Away: New York Mets @ {opponent}")

    # Network
    if api_override:
        nets = ", ".join(network_label(n) for n in api_override["networks"])
        lines.append(f"TV: {nets} [via MLB API]")
    else:
        net = entry.get("network", "TBD")
        lines.append(f"TV: {network_label(net)}")

    # Pre/post game
    if entry.get("pregame") and entry["pregame"] != "NO SHOW":
        lines.append(f"Pre-game: {entry['pregame']}")
    elif entry.get("pregame") == "NO SHOW":
        lines.append("Pre-game: No pre-game show")

    if entry.get("postgame"):
        lines.append(f"Post-game: {entry['postgame']}")

    lines.append("")
    lines.append("Go Mets!")
    return "\\n".join(lines)

def ical_escape(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")

def generate_ical(entries, api_overrides):
    DOCS_DIR.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Mets TV Schedule//mets-tv-schedule//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Mets 2026 TV Schedule",
        "X-WR-TIMEZONE:America/New_York",
        "X-WR-CALDESC:New York Mets 2026 broadcast schedule with TV network info",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]

    for entry in entries:
        if entry["opponent"] == "OFF" or not entry.get("time"):
            continue

        date = entry["date"]
        api_override = api_overrides.get(date)

        try:
            start = parse_time(date, entry["time"])
        except Exception:
            continue

        end = start + GAME_DURATION
        summary = ical_escape(make_summary(entry, api_override))
        description = make_description(entry, api_override)

        home_away = entry.get("home_away", "")
        if home_away == "home":
            location = "Citi Field\\, Queens\\, NY"
        else:
            location = f"@ {entry['opponent']}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{date}-mets-{entry['opponent'].lower().replace(' ', '-')}@mets-tv-schedule",
            f"DTSTAMP:{now}",
            f"DTSTART;TZID=America/New_York:{fmt_dt(start)}",
            f"DTEND;TZID=America/New_York:{fmt_dt(end)}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            f"LOCATION:{location}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")

    with open(OUTPUT_ICS, "w") as f:
        f.write("\r\n".join(lines) + "\r\n")

    print(f"Generated {OUTPUT_ICS} with {sum(1 for e in entries if e['opponent'] != 'OFF')} events")

if __name__ == "__main__":
    entries = load_manual_data()
    api_overrides = load_api_overrides()
    if api_overrides:
        print(f"Loaded {len(api_overrides)} API overrides")
    else:
        print("No API overrides — using manual schedule data")
    generate_ical(entries, api_overrides)
