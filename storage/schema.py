"""
storage/schema.py
SQLite table definitions for the playerStats engine.

One schema, one database per league. The db.py module handles
pointing each connection to the right league's .db file.

Tables:
  - players         : player identity (name, team, position, nationality)
  - teams           : team identity per league/season
  - matches         : fixture list with scores and dates
  - player_stats    : all per-season player stat rows (one row per player/season/stat_type)
  - team_stats      : all per-season team stat rows
  - shot_events     : individual shot records with xG and coordinates (for shot maps)
"""

CREATE_PLAYERS = """
CREATE TABLE IF NOT EXISTS players (
    player_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    player          TEXT    NOT NULL,
    team            TEXT,
    position        TEXT,
    nationality     TEXT,
    age             REAL,
    birth_year      INTEGER,
    league          TEXT    NOT NULL,
    season          TEXT    NOT NULL,
    UNIQUE(player, team, league, season)
);
"""

CREATE_TEAMS = """
CREATE TABLE IF NOT EXISTS teams (
    team_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    team            TEXT    NOT NULL,
    league          TEXT    NOT NULL,
    season          TEXT    NOT NULL,
    UNIQUE(team, league, season)
);
"""

CREATE_MATCHES = """
CREATE TABLE IF NOT EXISTS matches (
    match_id        INTEGER PRIMARY KEY,   -- football-data.org match ID
    match_date      TEXT,
    matchday        INTEGER,
    status          TEXT,
    home_team       TEXT,
    away_team       TEXT,
    home_score      INTEGER,
    away_score      INTEGER,
    home_xg         REAL,
    away_xg         REAL,
    league          TEXT    NOT NULL,
    season          TEXT    NOT NULL
);
"""

CREATE_PLAYER_STATS = """
CREATE TABLE IF NOT EXISTS player_stats (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    player                      TEXT    NOT NULL,
    team                        TEXT,
    league                      TEXT    NOT NULL,
    season                      TEXT    NOT NULL,
    stat_type                   TEXT    NOT NULL,   -- e.g. "standard", "shooting"

    -- Playing time
    matches_played              INTEGER,
    starts                      INTEGER,
    minutes                     REAL,
    nineties                    REAL,               -- minutes / 90

    -- Attacking
    goals                       REAL,
    assists                     REAL,
    goals_assists               REAL,
    np_goals                    REAL,
    penalties_scored            REAL,
    penalties_attempted         REAL,

    -- Expected stats
    xg                          REAL,
    np_xg                       REAL,
    xag                         REAL,
    xa                          REAL,
    np_xg_xag                   REAL,

    -- Overperformance
    goals_minus_xg              REAL,
    np_goals_minus_xg           REAL,
    assists_minus_xag           REAL,

    -- Per-90 rates
    goals_p90                   REAL,
    assists_p90                 REAL,
    xg_p90                      REAL,
    xag_p90                     REAL,

    -- Shooting
    shots                       REAL,
    shots_on_target             REAL,
    shots_on_target_pct         REAL,
    shots_p90                   REAL,
    shots_on_target_p90         REAL,
    goals_per_shot              REAL,
    goals_per_shot_on_target    REAL,
    avg_shot_distance           REAL,
    np_xg_per_shot              REAL,
    free_kick_shots             REAL,

    -- Passing
    passes_completed            REAL,
    passes_attempted            REAL,
    pass_completion_pct         REAL,
    pass_total_distance         REAL,
    pass_progressive_distance   REAL,
    key_passes                  REAL,
    passes_final_third          REAL,
    passes_penalty_area         REAL,
    crosses_penalty_area        REAL,
    progressive_passes          REAL,

    -- Goal & shot creating actions
    shot_creating_actions       REAL,
    sca_p90                     REAL,
    goal_creating_actions       REAL,
    gca_p90                     REAL,

    -- Defense
    tackles                     REAL,
    tackles_won                 REAL,
    tackles_def_third           REAL,
    tackles_mid_third           REAL,
    tackles_att_third           REAL,
    tackle_pct                  REAL,
    dribbles_challenged         REAL,
    dribbles_lost               REAL,
    blocks                      REAL,
    shots_blocked               REAL,
    passes_blocked              REAL,
    interceptions               REAL,
    tackles_interceptions       REAL,
    clearances                  REAL,
    errors                      REAL,

    -- Possession
    touches                     REAL,
    touches_def_pen             REAL,
    touches_def_third           REAL,
    touches_mid_third           REAL,
    touches_att_third           REAL,
    touches_att_pen             REAL,
    dribbles_attempted          REAL,
    dribbles_successful         REAL,
    dribble_success_pct         REAL,
    miscontrols                 REAL,
    dispossessed                REAL,
    passes_received             REAL,
    progressive_receptions      REAL,
    progressive_carries         REAL,
    carry_total_distance        REAL,
    carry_progressive_distance  REAL,

    -- Discipline / misc
    yellow_cards                REAL,
    red_cards                   REAL,
    second_yellow_cards         REAL,
    fouls_committed             REAL,
    fouls_drawn                 REAL,
    offsides                    REAL,
    crosses                     REAL,
    penalties_won               REAL,
    penalties_conceded          REAL,
    own_goals                   REAL,
    ball_recoveries             REAL,
    aerials_won                 REAL,
    aerials_lost                REAL,
    aerial_win_pct              REAL,

    -- Understat extras
    xg_understat                REAL,
    xa_understat                REAL,
    xg_chain                    REAL,
    xg_buildup                  REAL,

    UNIQUE(player, team, league, season, stat_type)
);
"""

CREATE_TEAM_STATS = """
CREATE TABLE IF NOT EXISTS team_stats (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    team                        TEXT    NOT NULL,
    league                      TEXT    NOT NULL,
    season                      TEXT    NOT NULL,
    stat_type                   TEXT    NOT NULL,

    -- Results (from Understat)
    matches_played              INTEGER,
    wins                        INTEGER,
    draws                       INTEGER,
    losses                      INTEGER,
    goals_for                   REAL,
    goals_against               REAL,
    points                      INTEGER,

    -- xG (from Understat)
    xg                          REAL,
    xga                         REAL,
    np_xg                       REAL,
    np_xga                      REAL,

    -- Press intensity (from Understat)
    ppda                        REAL,               -- passes per defensive action (lower = more press)
    oppda                       REAL,               -- opponent PPDA
    press_intensity             TEXT,               -- "High Press" / "Mid Press" / etc.
    deep                        REAL,               -- deep completions (passes into opp box)
    deep_allowed                REAL,

    -- Attacking (from FBref squads)
    goals                       REAL,
    shots                       REAL,
    shots_on_target             REAL,
    xg_fbref                    REAL,
    np_xg_fbref                 REAL,
    progressive_passes          REAL,
    progressive_carries         REAL,
    shot_creating_actions       REAL,
    goal_creating_actions       REAL,

    -- Defending (from FBref squads)
    tackles                     REAL,
    tackles_won                 REAL,
    interceptions               REAL,
    blocks                      REAL,
    clearances                  REAL,
    errors                      REAL,

    -- Standings (from football-data.org)
    position                    INTEGER,

    UNIQUE(team, league, season, stat_type)
);
"""

CREATE_SHOT_EVENTS = """
CREATE TABLE IF NOT EXISTS shot_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        TEXT,
    player          TEXT,
    team            TEXT,
    side            TEXT,               -- "home" or "away"
    minute          INTEGER,
    situation       TEXT,               -- e.g. "OpenPlay", "SetPiece", "Penalty"
    shot_type       TEXT,               -- e.g. "RightFoot", "LeftFoot", "Head"
    result          TEXT,               -- "Goal", "SavedShot", "MissedShots", "BlockedShot"
    x               REAL,               -- pitch x coordinate (metres, 0–105)
    y               REAL,               -- pitch y coordinate (metres, 0–68)
    xg              REAL,               -- xG value for this shot
    league          TEXT    NOT NULL,
    season          TEXT    NOT NULL
);
"""

# Indexes to speed up common queries
CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_player_stats_player  ON player_stats(player);",
    "CREATE INDEX IF NOT EXISTS idx_player_stats_team    ON player_stats(team);",
    "CREATE INDEX IF NOT EXISTS idx_player_stats_season  ON player_stats(season);",
    "CREATE INDEX IF NOT EXISTS idx_team_stats_team      ON team_stats(team);",
    "CREATE INDEX IF NOT EXISTS idx_shot_events_player   ON shot_events(player);",
    "CREATE INDEX IF NOT EXISTS idx_shot_events_team     ON shot_events(team);",
    "CREATE INDEX IF NOT EXISTS idx_shot_events_match    ON shot_events(match_id);",
    "CREATE INDEX IF NOT EXISTS idx_matches_date         ON matches(match_date);",
]

# Maps each table to the column(s) that make a row unique — mirrors the
# UNIQUE constraint (or PRIMARY KEY) on each CREATE TABLE above. db.py's
# upsert_df() uses this to build a real "ON CONFLICT ... DO UPDATE" so that
# re-running ingest after a normalizer/scraper fix actually updates existing
# rows instead of silently skipping them forever. Tables not listed here
# (currently just shot_events, which has no natural unique key yet) fall
# back to a plain append.
UNIQUE_KEYS = {
    "players":      ["player", "team", "league", "season"],
    "teams":        ["team", "league", "season"],
    "matches":      ["match_id"],
    "player_stats": ["player", "team", "league", "season", "stat_type"],
    "team_stats":   ["team", "league", "season", "stat_type"],
}

# Collect all CREATE statements for easy iteration in db.py
ALL_TABLES = [
    CREATE_PLAYERS,
    CREATE_TEAMS,
    CREATE_MATCHES,
    CREATE_PLAYER_STATS,
    CREATE_TEAM_STATS,
    CREATE_SHOT_EVENTS,
]
