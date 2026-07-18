"""
storage/db.py
Database connection manager and read/write helpers.

Every function accepts a league_name argument and automatically
resolves the correct .db file path via config.league_paths().
No other module needs to know where the database files live.

Usage examples:
    from storage.db import init_db, write_df, query

    # Initialise the database for a league (creates tables if not exist)
    init_db("Premier League")

    # Write a normalised DataFrame to a table
    write_df(df, table="player_stats", league_name="Premier League")

    # Query data back as a DataFrame
    df = query("SELECT * FROM player_stats WHERE season = '2024-2025'",
               league_name="Premier League")
"""

import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

from config import league_paths
from storage.schema import ALL_TABLES, CREATE_INDEXES, UNIQUE_KEYS

logger = logging.getLogger(__name__)


# ── Connection management ──────────────────────────────────────────────────────

def _db_path(league_name: str) -> Path:
    """Resolves the .db file path for a given league."""
    return league_paths(league_name)["db"]


@contextmanager
def _connect(league_name: str):
    """
    Context manager that opens a SQLite connection and closes it cleanly.
    Ensures the parent directory exists before connecting.

    Usage:
        with _connect("Premier League") as conn:
            conn.execute(...)
    """
    db_path = _db_path(league_name)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row          # rows accessible as dicts
    conn.execute("PRAGMA journal_mode=WAL") # better concurrent read performance
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema initialisation ──────────────────────────────────────────────────────

def init_db(league_name: str) -> None:
    """
    Creates all tables and indexes for a league database if they don't exist.
    Safe to call multiple times — uses CREATE IF NOT EXISTS throughout.

    Call this once before writing any data for a new league.
    """
    with _connect(league_name) as conn:
        for statement in ALL_TABLES:
            conn.execute(statement)
        for index in CREATE_INDEXES:
            conn.execute(index)
    logger.info(f"Database initialised: {_db_path(league_name)}")


def init_all_leagues() -> None:
    """Initialises databases for all five leagues plus cross_league."""
    from config import LEAGUE_FOLDERS
    for league_name in LEAGUE_FOLDERS:
        init_db(league_name)
    logger.info("All league databases initialised.")


# ── Write helpers ──────────────────────────────────────────────────────────────

def write_df(
    df: pd.DataFrame,
    table: str,
    league_name: str,
    if_exists: str = "append",
) -> int:
    """
    Writes a DataFrame to the specified table in the league's database.

    Args:
        df:          Normalized DataFrame (columns must match table schema).
        table:       Target table name, e.g. "player_stats".
        league_name: e.g. "Premier League"
        if_exists:   "append" (default) or "replace".
                     For incremental updates, use "append" — the UNIQUE
                     constraints in the schema prevent duplicates.

    Returns:
        Number of rows written.

    Notes:
        - Extra columns in df that don't exist in the table are silently dropped.
        - Missing columns are filled with NULL.
    """
    if df.empty:
        logger.warning(f"write_df called with empty DataFrame for table '{table}' — skipping.")
        return 0

    db_path = _db_path(league_name)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Filter df to only columns that exist in the target table
    with _connect(league_name) as conn:
        cursor = conn.execute(f"PRAGMA table_info({table})")
        valid_cols = {row["name"] for row in cursor.fetchall()}

    df_to_write = df[[c for c in df.columns if c in valid_cols]].copy()
    dropped     = set(df.columns) - valid_cols
    if dropped:
        logger.debug(f"Dropped columns not in schema: {dropped}")

    conn_str = f"sqlite:///{db_path}"
    df_to_write.to_sql(
        table,
        conn_str,
        if_exists=if_exists,
        index=False,
        method="multi",
        chunksize=500,
    )

    logger.info(f"Wrote {len(df_to_write)} rows → {table} ({league_name})")
    return len(df_to_write)


def upsert_df(df: pd.DataFrame, table: str, league_name: str) -> int:
    """
    Inserts rows, UPDATING existing ones on conflict (based on the table's
    natural key in schema.UNIQUE_KEYS) rather than silently discarding new
    data for keys that already exist.

    This matters specifically for iterative development: after fixing a
    normalizer or scraper bug, re-running ingest should actually correct
    the rows already in the database, not leave them frozen with whatever
    (possibly wrong) values they had before. Tables with no defined key
    (currently just shot_events) fall back to a plain append, same as
    previous behaviour there.

    Returns the number of rows actually changed (insert + update), from
    SQLite's own change counter — not just len(df). A previous version of
    this function returned len(df) regardless of what actually landed,
    which is exactly how a NOT NULL constraint violation on every row
    stayed invisible for several ingestion runs. If this number doesn't
    match what you expect, something upstream (usually the normalizer) is
    producing rows SQLite is rejecting or silently not matching columns —
    check the logs above this line before assuming the data is correct.
    """
    if df.empty:
        return 0

    with _connect(league_name) as conn:
        cursor  = conn.execute(f"PRAGMA table_info({table})")
        valid_cols = [row["name"] for row in cursor.fetchall() if row["name"] != "id"]

    df_to_write = df[[c for c in df.columns if c in valid_cols]].copy()
    if df_to_write.empty:
        logger.warning(
            f"upsert_df: none of the DataFrame's columns matched '{table}' "
            f"schema — nothing written. DataFrame had: {list(df.columns)}"
        )
        return 0

    cols_str     = ", ".join(df_to_write.columns)
    placeholders = ", ".join(["?" for _ in df_to_write.columns])

    conflict_cols = UNIQUE_KEYS.get(table)
    if conflict_cols and all(c in df_to_write.columns for c in conflict_cols):
        update_cols = [c for c in df_to_write.columns if c not in conflict_cols]
        if update_cols:
            set_clause = ", ".join(f"{c}=excluded.{c}" for c in update_cols)
            sql = (
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
                f"ON CONFLICT({', '.join(conflict_cols)}) DO UPDATE SET {set_clause}"
            )
        else:
            # Every written column is part of the key — nothing to update
            sql = (
                f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders}) "
                f"ON CONFLICT({', '.join(conflict_cols)}) DO NOTHING"
            )
    else:
        # No known unique key for this table (e.g. shot_events) — plain append
        sql = f"INSERT INTO {table} ({cols_str}) VALUES ({placeholders})"

    with _connect(league_name) as conn:
        before = conn.total_changes
        conn.executemany(sql, df_to_write.itertuples(index=False, name=None))
        written = conn.total_changes - before

    logger.info(
        f"Upserted {written} rows → {table} ({league_name}) "
        f"[{len(df_to_write)} attempted]"
    )
    return written


# ── Read helpers ───────────────────────────────────────────────────────────────

def query(sql: str, league_name: str, params: tuple = ()) -> pd.DataFrame:
    """
    Runs a SQL SELECT query and returns the result as a DataFrame.

    Args:
        sql:         SQL query string. Use ? for parameters.
        league_name: e.g. "Premier League"
        params:      Tuple of values to bind to ? placeholders.

    Example:
        df = query(
            "SELECT player, xg, goals FROM player_stats WHERE season = ? AND stat_type = ?",
            "Premier League",
            params=("2024-2025", "standard")
        )
    """
    db_path = _db_path(league_name)
    if not db_path.exists():
        raise FileNotFoundError(
            f"No database found at {db_path}. "
            f"Run init_db('{league_name}') first."
        )
    with _connect(league_name) as conn:
        df = pd.read_sql_query(sql, conn, params=params)
    return df


def get_players(
    league_name: str,
    season: str,
    stat_type: str = "standard",
    min_minutes: int = 0,
) -> pd.DataFrame:
    """
    Convenience query — fetches player stats for a league/season.

    Args:
        league_name: e.g. "Premier League"
        season:      e.g. "2024-2025"
        stat_type:   e.g. "standard", "shooting", "passing" (default: "standard")
        min_minutes: Filter out players with fewer than this many minutes.

    Returns:
        DataFrame of player stats rows.
    """
    sql = """
        SELECT *
        FROM   player_stats
        WHERE  league    = ?
          AND  season    = ?
          AND  stat_type = ?
          AND  (minutes IS NULL OR minutes >= ?)
        ORDER BY minutes DESC
    """
    return query(sql, league_name, params=(league_name, season, stat_type, min_minutes))


def get_teams(
    league_name: str,
    season: str,
    stat_type: str = "standard",
) -> pd.DataFrame:
    """Convenience query — fetches team stats for a league/season."""
    sql = """
        SELECT *
        FROM   team_stats
        WHERE  league    = ?
          AND  season    = ?
          AND  stat_type = ?
        ORDER BY position ASC NULLS LAST
    """
    return query(sql, league_name, params=(league_name, season, stat_type))


def get_shots(
    league_name: str,
    season: str,
    team: str | None = None,
    player: str | None = None,
) -> pd.DataFrame:
    """
    Fetches shot events, optionally filtered by team or player.
    Used by the shot map visualisation.
    """
    conditions = ["league = ?", "season = ?"]
    params: list = [league_name, season]

    if team:
        conditions.append("team = ?")
        params.append(team)
    if player:
        conditions.append("player = ?")
        params.append(player)

    sql = f"SELECT * FROM shot_events WHERE {' AND '.join(conditions)}"
    return query(sql, league_name, params=tuple(params))


def get_matches(
    league_name: str,
    season: str,
    status: str | None = None,
) -> pd.DataFrame:
    """Fetches fixtures, optionally filtered by status (e.g. 'FINISHED')."""
    conditions = ["league = ?", "season = ?"]
    params: list = [league_name, season]

    if status:
        conditions.append("status = ?")
        params.append(status)

    sql = f"SELECT * FROM matches WHERE {' AND '.join(conditions)} ORDER BY match_date"
    return query(sql, league_name, params=tuple(params))


# ── Utility ────────────────────────────────────────────────────────────────────

def table_counts(league_name: str) -> pd.DataFrame:
    """
    Returns a summary of how many rows are in each table.
    Useful for a quick sanity check after ingestion.

    Example output:
        table             rows
        players           532
        player_stats      4788
        team_stats        120
        shot_events       9241
        matches           380
    """
    tables = ["players", "teams", "matches", "player_stats", "team_stats", "shot_events"]
    rows = []
    with _connect(league_name) as conn:
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                rows.append({"table": t, "rows": count})
            except sqlite3.OperationalError:
                rows.append({"table": t, "rows": "table missing"})
    return pd.DataFrame(rows)


def drop_season(league_name: str, season: str) -> None:
    """
    Deletes all data for a specific season from all tables.
    Useful for re-ingesting a season from scratch.
    """
    tables_with_season = [
        "players", "teams", "matches",
        "player_stats", "team_stats", "shot_events",
    ]
    with _connect(league_name) as conn:
        for table in tables_with_season:
            conn.execute(f"DELETE FROM {table} WHERE season = ?", (season,))
    logger.info(f"Dropped all {season} data from {league_name} database.")
