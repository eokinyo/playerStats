# playerStats: football player and team analytics

A Python toolkit for analysing advanced football data across the top five European leagues (Premier League, La Liga, Bundesliga, Serie A, Ligue 1): data ingestion, a local SQLite store, player, team and league statistics, xG analysis and charts.

It is a non-commercial, personal analysis project.

## Data sources

| Source | What it provides | Method |
|---|---|---|
| [FBref](https://fbref.com) | xG, xA, progressive stats, pressures, GCA, per-90 figures | HTML scraping, with a 3-second delay between requests |
| [Understat](https://understat.com) | Shot-level xG, shot maps, match xG timeline | Parsing the JSON embedded in public pages |
| [football-data.org](https://www.football-data.org) | Fixtures, results, standings | REST API (free tier, needs your own key) |

No data is committed to this repository. Data is fetched when you run the ingestion step and stored locally.

**Data terms.** Each source has its own terms of use, and they apply to any data you download with this code. Understat and FBref data are used here for non-commercial personal analysis only. Check each provider's terms before reusing or republishing data or charts built from it.

## Setup (Windows PowerShell)

The virtual environment lives outside the project folder, in `%LOCALAPPDATA%\venvs`:

    git clone https://github.com/eokinyo/playerStats.git
    cd playerStats
    py -m venv $env:LOCALAPPDATA\venvs\playerStats
    & $env:LOCALAPPDATA\venvs\playerStats\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env   # then put your own football-data.org API key in .env

`.env` is git-ignored. Never commit a real key.

On macOS or Linux, use `python3 -m venv ~/.cache/venvs/playerStats`, `source ~/.cache/venvs/playerStats/bin/activate` and `cp .env.example .env`.

## Usage

    # Ingest data for a season
    python main.py ingest --league "Premier League" --season 2024-2025

    # Player rankings (minimum 450 minutes played)
    python main.py analyse players --league "Premier League" --min-minutes 450

    # Shot map for a team
    python main.py viz shotmap --team "Arsenal" --season 2024-2025

    # Cross-league comparison
    python main.py analyse leagues --stat xg_per90

## Project structure

    config.py         settings
    ingestion/        scrapers, API client and normaliser
    storage/          SQLite schema and database helpers
    analysis/         player, team, league and xG statistics
    visualisation/    charts and pitch plots
    main.py           command-line entry point

## Licence

No licence has been chosen for this repository yet, so all rights are reserved by default. Third-party data fetched by the code is not covered by any licence here and stays under each provider's terms.
