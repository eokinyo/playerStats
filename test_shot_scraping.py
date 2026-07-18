"""
test_shot_scraping.py — standalone diagnostic, not part of the pipeline.

Step 1: scrape_league_matches() should already work (rewritten earlier to
use the same getLeagueData API as players/teams) — use it to get one real
match_id to test with.

Step 2: try scrape_match_shots() on that match_id as it currently stands
(still the old embedded-JSON approach) and see exactly how it fails, if
it does — same discipline as before: check first, don't rewrite blind.
"""

from ingestion.understat_scraper import scrape_league_matches, scrape_match_shots

LEAGUE = "Premier League"
SEASON = "2024-2025"

print("Fetching match list...")
matches = scrape_league_matches(LEAGUE, SEASON)
print(f"Got {len(matches)} matches.\n")
print(matches.head(3).to_string())

# Grab a match that's actually been played
played = matches[matches["is_played"] == True] if "is_played" in matches.columns else matches
if played.empty:
    played = matches
sample = played.iloc[0]
match_id = sample["match_id"]
print(f"\nUsing match_id={match_id}  ({sample['home_team']} vs {sample['away_team']})")

print(f"\nTrying scrape_match_shots({match_id!r}, ...)...")
try:
    shots = scrape_match_shots(match_id, LEAGUE, SEASON)
    print(f"SUCCESS — got {len(shots)} shots")
    print(shots.head(10).to_string())
except Exception as e:
    print(f"FAILED: {type(e).__name__}: {e}")
