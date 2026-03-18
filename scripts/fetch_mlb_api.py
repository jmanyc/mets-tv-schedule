#!/usr/bin/env python3
"""
Fetch the Mets 2026 schedule from the MLB Stats API and save to data/mlb_api_schedule.json.
Run by the GitHub Action daily. Only overwrites the file if meaningful broadcast data is found.
"""

import json
import urllib.request
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT = DATA_DIR / "mlb_api_schedule.json"

API_URL = (
    "https://statsapi.mlb.com/api/v1/schedule"
    "?lang=en&sportIds=1"
    "&hydrate=team(venue(timezone)),venue(timezone),"
    "game(seriesStatus,seriesSummary,content(summary,media(epg))),"
    "seriesStatus,seriesSummary,broadcasts(all),linescore,radioBroadcasts"
    "&season=2026"
    "&startDate=2026-03-25&endDate=2026-09-30"
    "&teamId=121"
    "&timeZone=America/New_York"
    "&eventTypes=primary&scheduleTypes=games"
)

METS_LOCAL_NETWORKS = {"SNY", "PIX11"}
SNY_MINIMUM_GAMES = 20  # require at least this many SNY listings to avoid acting on partial updates

def count_sny_games(data):
    """Count games that have SNY or PIX11 TV listings in the API response."""
    count = 0
    for date_entry in data.get("dates", []):
        for game in date_entry.get("games", []):
            for b in game.get("broadcasts", []):
                if b.get("name") in METS_LOCAL_NETWORKS and b.get("type") == "TV":
                    count += 1
                    break  # only count each game once
    return count

def fetch():
    print(f"Fetching MLB API...")
    req = urllib.request.Request(API_URL, headers={"User-Agent": "mets-tv-schedule/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    total = data.get("totalItems", 0)
    print(f"  Got {total} games")

    sny_count = count_sny_games(data)
    print(f"  SNY/PIX11 listings found: {sny_count}")

    if sny_count >= SNY_MINIMUM_GAMES:
        print(f"  Threshold met ({sny_count} >= {SNY_MINIMUM_GAMES}) — saving API schedule")
        with open(OUTPUT, "w") as f:
            json.dump(data, f, indent=2)
        return True
    else:
        print(f"  Threshold not met ({sny_count} < {SNY_MINIMUM_GAMES}) — skipping save (manual schedule still active)")
        return False

if __name__ == "__main__":
    found = fetch()
    sys.exit(0)  # always exit 0 — "no SNY data yet" is expected, not an error
