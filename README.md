# Football Stat Engine

A Python stat engine for analysing advanced football data across the top 5 European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1).

Built for curiosity-driven analysis and social media visualisations. No paywalls — all data sourced from FBref, Understat, and the free tier of football-data.org.

## Data sources
| Source | What it provides | Method |
|---|---|---|
| [FBref](https://fbref.com) | xG, xA, progressive stats, pressures, GCA, per-90s | HTML scraping |
| [Understat](https://understat.com) | Shot-level xG, shot maps, match xG timeline | JSON embed parsing |
| [football-data.org](https://football-data.org) | Fixtures, results, standings | REST API (free key) |

## Setup

```bash
git clone <your-repo>
cd football_stat_engine
pip install -r requirements.txt
cp .env.example .env   # add your football-data.org API key
```

## Usage

```bash
# Ingest data for the current season
python main.py ingest --league "Premier League" --season 2024-2025

# Run player rankings
python main.py analyse players --league "Premier League" --min-minutes 450

# Generate shot map for a team
python main.py viz shotmap --team "Arsenal" --season 2024-2025

# Cross-league comparison
python main.py analyse leagues --stat xg_per90
```

## Project structure
```
football_stat_engine/
├── config.py           # all settings live here
├── ingestion/          # scrapers and normalizer
├── storage/            # SQLite schema and db helpers
├── analysis/           # stat calculations
├── visualisation/      # charts and pitch plots
└── output/             # saved reports and images
```

## Notes
- FBref scraping includes a 3-second delay between requests out of respect for their servers.
- This project is strictly non-commercial. Data is used for personal analysis and shared insights only.
- Minimum 450 minutes filter applied to player rankings to exclude bit-part players.