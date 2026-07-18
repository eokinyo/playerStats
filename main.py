"""
main.py — CLI entry point for the playerStats engine.

Usage examples:
    python main.py ingest --league "Premier League" --season 2024-2025
    python main.py ingest --all --season 2024-2025

    python main.py analyse players --league "Premier League" --metric xg_p90
    python main.py analyse teams   --league "La Liga"
    python main.py analyse xg      --league "Bundesliga"
    python main.py analyse leagues --season 2024-2025

    python main.py viz radar   --league "Premier League" --player "Erling Haaland"
    python main.py viz scatter --league "Premier League"
    python main.py viz shotmap --league "Premier League" --team "Arsenal"
    python main.py viz style   --league "La Liga"
    python main.py viz form    --league "Premier League" --team "Liverpool"
    python main.py viz europe  --metric xg_p90

    python main.py db init --league "Premier League"
    python main.py db init --all
    python main.py db status --league "Premier League"
"""

import argparse
import logging
import sys
from pathlib import Path

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Config import (everything else imports from here) ─────────────────────────
from config import LEAGUES, CURRENT_SEASON, league_paths


# ══════════════════════════════════════════════════════════════════════════════
# DB commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_db_init(args):
    """Initialises the SQLite database(s) — creates tables if they don't exist."""
    from storage.db import init_db, init_all_leagues

    if args.all:
        print("Initialising all league databases...")
        init_all_leagues()
        print("✓ All databases ready.")
    else:
        league = args.league
        print(f"Initialising database for {league}...")
        init_db(league)
        paths = league_paths(league)
        print(f"✓ Database ready: {paths['db']}")


def cmd_db_status(args):
    """Prints row counts for all tables in a league database."""
    from storage.db import table_counts

    league = args.league
    print(f"\n── {league} database status ──")
    df = table_counts(league)
    print(df.to_string(index=False))
    print()


# ══════════════════════════════════════════════════════════════════════════════
# Ingest commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_ingest(args):
    """
    Scrapes data from Understat and writes it to the database.

    NOTE: FBref scraping was dropped — FBref sits behind Cloudflare Turnstile,
    an interactive JS challenge that neither TLS impersonation (curl_cffi) nor
    a stealth-patched real browser (Patchright) could reliably clear. Understat
    alone covers goals, assists, shots, xG, xA, and team-level xG/xGA/pressing
    (ppda) — sufficient for the core analysis and visualisation this project
    is built around.
    """
    from ingestion.understat_scraper import scrape_league_players, scrape_league_teams
    from ingestion.normalizer import (
        normalize_understat_players, normalize_understat_teams,
        apply_minutes_filter,
    )
    from storage.db import init_db, upsert_df

    season  = args.season
    leagues = list(LEAGUES.keys()) if args.all else [args.league]

    for league in leagues:
        print(f"\n{'─' * 60}")
        print(f"  Ingesting: {league}  |  Season: {season}")
        print(f"{'─' * 60}")

        # Ensure database exists
        init_db(league)

        # ── Understat player stats ─────────────────────────────────────────
        print("\n[1/2] Understat player stats...")
        try:
            us_players = scrape_league_players(league, season)
            us_players = normalize_understat_players(us_players)
            n = upsert_df(us_players, "player_stats", league)
            print(f"      ✓ {n} Understat player rows written")
        except Exception as e:
            print(f"      ✗ Understat players failed: {e}")

        # ── Understat team stats ───────────────────────────────────────────
        print("\n[2/2] Understat team stats...")
        try:
            us_teams = scrape_league_teams(league, season)
            us_teams = normalize_understat_teams(us_teams)
            n = upsert_df(us_teams, "team_stats", league)
            print(f"      ✓ {n} Understat team rows written")
        except Exception as e:
            print(f"      ✗ Understat teams failed: {e}")

        print(f"\n✓ {league} ingestion complete.")

    print("\n✓ All done.")


def cmd_ingest_fixtures(args):
    """Fetches fixtures and standings from football-data.org API."""
    from ingestion.footballdata_api import fetch_fixtures, fetch_standings
    from storage.db import init_db, upsert_df

    season  = args.season
    leagues = list(LEAGUES.keys()) if args.all else [args.league]

    for league in leagues:
        print(f"\nFetching fixtures: {league} {season}...")
        init_db(league)
        try:
            fixtures = fetch_fixtures(league, season)
            n = upsert_df(fixtures, "matches", league)
            print(f"  ✓ Fixtures: {n} rows")

            standings = fetch_standings(league, season)
            n = upsert_df(standings, "team_stats", league)
            print(f"  ✓ Standings: {n} rows")
        except Exception as e:
            print(f"  ✗ Failed for {league}: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Analyse commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_analyse_players(args):
    """Prints player rankings to the terminal and optionally exports CSV."""
    from analysis.player_stats import (
        top_scorers, top_assisters, shot_creation_leaders,
        progressive_action_leaders, defensive_leaders,
        overperformers, season_summary,
    )

    league  = args.league
    season  = args.season
    metric  = args.metric or "goals"
    top_n   = args.top_n or 20
    min_min = args.min_minutes or 450

    print(f"\n── Player Analysis: {league} {season} ──\n")

    # Season summary header
    summary = season_summary(league, season, min_minutes=min_min)
    if summary:
        print(f"  Players analysed : {summary.get('total_players', '?')}")
        print(f"  Total goals      : {summary.get('total_goals', '?')}")
        print(f"  Total xG         : {summary.get('total_xg', '?')}")
        print(f"  Top scorer       : {summary.get('most_goals', '?')}")
        print(f"  Most xG          : {summary.get('most_xg', '?')}")
        print(f"  Top creator      : {summary.get('top_creator', '?')}")
        print()

    # Dispatch to right ranking function
    dispatch = {
        "goals":                   lambda: top_scorers(league, season, top_n, min_min),
        "assists":                 lambda: top_assisters(league, season, top_n, min_min),
        "xg":                      lambda: top_scorers(league, season, top_n, min_min),
        "xg_p90":                  lambda: top_scorers(league, season, top_n, min_min),
        "sca_p90":                 lambda: shot_creation_leaders(league, season, top_n, min_min),
        "progressive_actions_p90": lambda: progressive_action_leaders(league, season, top_n, min_min),
        "tackles_interceptions":   lambda: defensive_leaders(league, season, top_n, min_min),
        "overperformers_goals":    lambda: overperformers(league, season, "goals", top_n, min_min),
        "overperformers_assists":  lambda: overperformers(league, season, "assists", top_n, min_min),
    }

    fn = dispatch.get(metric, lambda: top_scorers(league, season, top_n, min_min))
    df = fn()

    if df.empty:
        print("No data found. Have you run 'ingest' for this league and season?")
        return

    print(df.to_string(index=False))

    # Optional CSV export
    if args.export:
        out_path = league_paths(league)["reports"] / f"players_{metric}_{season}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"\n✓ Exported: {out_path}")


def cmd_analyse_teams(args):
    """Prints team analysis to terminal."""
    from analysis.team_stats import (
        league_table, team_style_fingerprint,
        pressing_rankings, attack_profiles, defence_profiles, form_table,
    )

    league = args.league
    season = args.season
    view   = args.view or "table"

    print(f"\n── Team Analysis: {league} {season} ──\n")

    views = {
        "table":    lambda: league_table(league, season),
        "style":    lambda: team_style_fingerprint(league, season),
        "pressing": lambda: pressing_rankings(league, season),
        "attack":   lambda: attack_profiles(league, season),
        "defence":  lambda: defence_profiles(league, season),
        "form":     lambda: form_table(league, season),
    }

    fn = views.get(view, views["table"])
    df = fn()

    if df.empty:
        print("No data found. Run 'ingest' first.")
        return

    print(df.to_string(index=False))

    if args.export:
        out_path = league_paths(league)["reports"] / f"teams_{view}_{season}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"\n✓ Exported: {out_path}")


def cmd_analyse_xg(args):
    """Runs xG analysis for a league."""
    from analysis.xg_analysis import (
        xg_league_summary, finishing_skill_table,
        chance_creation_vs_conversion,
    )

    league = args.league
    season = args.season
    view   = args.view or "summary"

    print(f"\n── xG Analysis: {league} {season} ──\n")

    views = {
        "summary":    lambda: xg_league_summary(league, season),
        "finishing":  lambda: finishing_skill_table(league, season),
        "creation":   lambda: chance_creation_vs_conversion(league, season),
    }

    fn = views.get(view, views["summary"])
    df = fn()

    if df.empty:
        print("No xG data found. Run 'ingest' first.")
        return

    print(df.to_string(index=False))

    if args.export:
        out_path = league_paths(league)["reports"] / f"xg_{view}_{season}.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        print(f"\n✓ Exported: {out_path}")


def cmd_analyse_leagues(args):
    """Cross-league comparison analysis."""
    from analysis.league_stats import (
        league_xg_comparison, league_pressing_comparison,
        league_goals_vs_xg, top_players_across_leagues,
    )

    season = args.season
    view   = args.view or "xg"

    print(f"\n── Cross-League Analysis: {season} ──\n")

    views = {
        "xg":       lambda: league_xg_comparison(season),
        "pressing": lambda: league_pressing_comparison(season),
        "goals_xg": lambda: league_goals_vs_xg(season),
        "top":      lambda: top_players_across_leagues(
                        season,
                        metric=args.metric or "xg_p90",
                        top_n=args.top_n or 20,
                    ),
    }

    fn = views.get(view, views["xg"])
    df = fn()

    if df.empty:
        print("No cross-league data. Ingest at least two leagues first.")
        return

    print(df.to_string(index=False))


# ══════════════════════════════════════════════════════════════════════════════
# Visualisation commands
# ══════════════════════════════════════════════════════════════════════════════

def cmd_viz_radar(args):
    """Generates a player radar / percentile chart."""
    from visualisation.player_charts import radar_chart

    league  = args.league
    season  = args.season
    player  = args.player
    compare = args.compare or None

    if not player:
        print("Error: --player is required for radar charts.")
        sys.exit(1)

    print(f"Generating radar chart: {player}...")
    fig = radar_chart(player, league, season, compare_player=compare, save=True)
    paths = league_paths(league)
    print(f"✓ Saved to {paths['charts']}/")
    plt_show(fig, args)


def cmd_viz_scatter(args):
    """Generates a Goals vs xG scatter plot."""
    from visualisation.player_charts import xg_vs_goals_scatter

    league = args.league
    season = args.season
    print(f"Generating Goals vs xG scatter: {league} {season}...")
    fig = xg_vs_goals_scatter(league, season, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_lollipop(args):
    """Generates an over/underperformance lollipop chart."""
    from visualisation.player_charts import overperformance_bar

    league = args.league
    season = args.season
    metric = args.metric or "goals"
    print(f"Generating overperformance chart: {league} {season} ({metric})...")
    fig = overperformance_bar(league, season, metric=metric, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_ranking(args):
    """Generates a horizontal bar ranking chart."""
    from visualisation.player_charts import ranking_bar

    league = args.league
    season = args.season
    metric = args.metric or "goals"
    label  = args.label  or metric.replace("_", " ").title()
    print(f"Generating ranking bars: {league} {season} ({metric})...")
    fig = ranking_bar(league, season, metric=metric, label=label, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_style(args):
    """Generates a team style quadrant map."""
    from visualisation.team_charts import attack_vs_defence_scatter

    league = args.league
    season = args.season
    print(f"Generating style quadrant map: {league} {season}...")
    fig = attack_vs_defence_scatter(league, season, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_bubble(args):
    """Generates an attack vs defence bubble chart."""
    from visualisation.team_charts import attack_vs_defence_bubble

    league = args.league
    season = args.season
    print(f"Generating attack vs defence bubble: {league} {season}...")
    fig = attack_vs_defence_bubble(league, season, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_form(args):
    """Generates a team form timeline chart."""
    from visualisation.team_charts import form_chart

    league = args.league
    season = args.season
    team   = args.team

    if not team:
        print("Error: --team is required for form charts.")
        sys.exit(1)

    print(f"Generating form timeline: {team} {season}...")
    fig = form_chart(team=team, league_name=league, season=season, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_pressing(args):
    """Generates a pressing intensity bar chart."""
    from visualisation.team_charts import pressing_bar

    league = args.league
    season = args.season
    print(f"Generating pressing chart: {league} {season}...")
    fig = pressing_bar(league, season, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_shotmap(args):
    """Generates a shot map for a team or player."""
    from visualisation.shot_maps import team_shot_map, player_shot_map

    league = args.league
    season = args.season

    if args.player:
        print(f"Generating player shot map: {args.player}...")
        fig = player_shot_map(player=args.player, league_name=league, season=season, save=True)
    elif args.team:
        half = args.half or "attack"
        print(f"Generating team shot map: {args.team} ({half})...")
        fig = team_shot_map(team=args.team, league_name=league, season=season, half=half, save=True)
    else:
        print("Error: --team or --player required for shot maps.")
        sys.exit(1)

    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_heatmap(args):
    """Generates an xG heatmap for a team."""
    from visualisation.shot_maps import xg_heatmap

    league = args.league
    season = args.season
    print(f"Generating xG heatmap: {args.team or 'all'} {season}...")
    fig = xg_heatmap(league, season, team=args.team, save=True)
    print(f"✓ Saved to {league_paths(league)['charts']}/")
    plt_show(fig, args)


def cmd_viz_europe(args):
    """Generates a European ranking bars chart."""
    from visualisation.league_charts import european_ranking_bars

    season       = args.season
    metric       = args.metric       or "xg_p90"
    metric_label = args.label        or metric.replace("_", " ").title()
    position     = args.position     or None
    top_n        = args.top_n        or 20

    print(f"Generating European ranking: {metric} {season}...")
    fig = european_ranking_bars(
        season, metric=metric, metric_label=metric_label,
        top_n=top_n, position_group=position, save=True,
    )
    from config import league_paths as lp
    print(f"✓ Saved to output/cross_league/charts/")
    plt_show(fig, args)


def cmd_viz_league_radar(args):
    """Generates a league style radar chart."""
    from visualisation.league_charts import league_style_radar

    season = args.season
    print(f"Generating league style radar: {season}...")
    fig = league_style_radar(season, save=True)
    print("✓ Saved to output/cross_league/charts/")
    plt_show(fig, args)


def cmd_viz_violin(args):
    """Generates a cross-league stat distribution violin plot."""
    from visualisation.league_charts import stat_distribution_violin

    season       = args.season
    metric       = args.metric or "xg_p90"
    metric_label = args.label  or metric.replace("_", " ").title()

    print(f"Generating violin distribution: {metric} {season}...")
    fig = stat_distribution_violin(
        season, metric=metric, metric_label=metric_label, save=True
    )
    print("✓ Saved to output/cross_league/charts/")
    plt_show(fig, args)


def cmd_viz_xg_leagues(args):
    """Generates a goals vs xG by league chart."""
    from visualisation.league_charts import goals_vs_xg_by_league

    season = args.season
    print(f"Generating goals vs xG by league: {season}...")
    fig = goals_vs_xg_by_league(season, save=True)
    print("✓ Saved to output/cross_league/charts/")
    plt_show(fig, args)


def plt_show(fig, args):
    """Optionally shows the chart in a window if --show flag is passed."""
    if getattr(args, "show", False):
        import matplotlib.pyplot as plt
        plt.show()
    else:
        import matplotlib.pyplot as plt
        plt.close(fig)


# ══════════════════════════════════════════════════════════════════════════════
# Argument parser
# ══════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="playerStats",
        description="Football stat engine — top 5 European leagues.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season", default=CURRENT_SEASON,
        help=f"Season string, e.g. 2024-2025 (default: {CURRENT_SEASON})",
    )
    parser.add_argument("--show", action="store_true",
                        help="Open chart in a window after saving")

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── db ────────────────────────────────────────────────────────────────────
    db_p = sub.add_parser("db", help="Database management")
    db_sub = db_p.add_subparsers(dest="db_command", metavar="ACTION")
    db_sub.required = True

    db_init = db_sub.add_parser("init", help="Initialise database(s)")
    db_init.add_argument("--league", choices=list(LEAGUES.keys()))
    db_init.add_argument("--all", action="store_true", help="All leagues")
    db_init.set_defaults(func=cmd_db_init)

    db_status = db_sub.add_parser("status", help="Show row counts per table")
    db_status.add_argument("--league", required=True, choices=list(LEAGUES.keys()))
    db_status.set_defaults(func=cmd_db_status)

    # ── ingest ────────────────────────────────────────────────────────────────
    ing = sub.add_parser("ingest", help="Scrape and store stats")
    ing.add_argument("--league", choices=list(LEAGUES.keys()))
    ing.add_argument("--all", action="store_true", help="All leagues")
    ing.add_argument("--season", default=CURRENT_SEASON,
                     help=f"Season string, e.g. 2024-2025 (default: {CURRENT_SEASON})")
    ing.add_argument("--fixtures", action="store_true",
                     help="Fetch fixtures from football-data.org instead")
    ing.set_defaults(func=lambda a: cmd_ingest_fixtures(a) if a.fixtures else cmd_ingest(a))

    # ── analyse ───────────────────────────────────────────────────────────────
    an = sub.add_parser("analyse", help="Run analysis")
    an_sub = an.add_subparsers(dest="analyse_command", metavar="TYPE")
    an_sub.required = True

    # players
    an_p = an_sub.add_parser("players", help="Player rankings and profiles")
    an_p.add_argument("--league", required=True, choices=list(LEAGUES.keys()))
    an_p.add_argument("--season", default=CURRENT_SEASON)
    an_p.add_argument("--metric", default="goals",
                      help="Metric to rank by (default: goals)")
    an_p.add_argument("--top-n", type=int, default=20)
    an_p.add_argument("--min-minutes", type=int, default=450)
    an_p.add_argument("--export", action="store_true", help="Export CSV to reports/")
    an_p.set_defaults(func=cmd_analyse_players)

    # teams
    an_t = an_sub.add_parser("teams", help="Team analysis")
    an_t.add_argument("--league", required=True, choices=list(LEAGUES.keys()))
    an_t.add_argument("--season", default=CURRENT_SEASON)
    an_t.add_argument("--view", default="table",
                      choices=["table", "style", "pressing", "attack", "defence", "form"])
    an_t.add_argument("--export", action="store_true")
    an_t.set_defaults(func=cmd_analyse_teams)

    # xg
    an_x = an_sub.add_parser("xg", help="xG deep-dive")
    an_x.add_argument("--league", required=True, choices=list(LEAGUES.keys()))
    an_x.add_argument("--season", default=CURRENT_SEASON)
    an_x.add_argument("--view", default="summary",
                      choices=["summary", "finishing", "creation"])
    an_x.add_argument("--export", action="store_true")
    an_x.set_defaults(func=cmd_analyse_xg)

    # leagues
    an_l = an_sub.add_parser("leagues", help="Cross-league comparison")
    an_l.add_argument("--season", default=CURRENT_SEASON)
    an_l.add_argument("--view", default="xg",
                      choices=["xg", "pressing", "goals_xg", "top"])
    an_l.add_argument("--metric", default="xg_p90")
    an_l.add_argument("--top-n", type=int, default=20)
    an_l.set_defaults(func=cmd_analyse_leagues)

    # ── viz ───────────────────────────────────────────────────────────────────
    vz = sub.add_parser("viz", help="Generate charts")
    vz_sub = vz.add_subparsers(dest="viz_command", metavar="CHART")
    vz_sub.required = True

    def _vz(name, help_text, fn, league=True, extras=None):
        p = vz_sub.add_parser(name, help=help_text)
        if league:
            p.add_argument("--league", required=True, choices=list(LEAGUES.keys()))
        p.add_argument("--season", default=CURRENT_SEASON)
        p.add_argument("--show", action="store_true", help="Open chart window")
        if extras:
            extras(p)
        p.set_defaults(func=fn)
        return p

    _vz("radar", "Player percentile radar chart", cmd_viz_radar,
        extras=lambda p: [
            p.add_argument("--player", required=True),
            p.add_argument("--compare", help="Second player to overlay"),
        ])

    _vz("scatter", "Goals vs xG scatter plot", cmd_viz_scatter)

    _vz("lollipop", "Over/underperformance lollipop chart", cmd_viz_lollipop,
        extras=lambda p: [
            p.add_argument("--metric", default="goals", choices=["goals", "assists"]),
        ])

    _vz("ranking", "Player ranking bar chart", cmd_viz_ranking,
        extras=lambda p: [
            p.add_argument("--metric", default="goals"),
            p.add_argument("--label", help="Axis label"),
        ])

    _vz("style", "Team style quadrant map", cmd_viz_style)

    _vz("bubble", "Attack vs defence bubble chart", cmd_viz_bubble)

    _vz("form", "Team form timeline", cmd_viz_form,
        extras=lambda p: [
            p.add_argument("--team", required=True),
        ])

    _vz("pressing", "Pressing intensity bar chart", cmd_viz_pressing)

    _vz("shotmap", "Shot map (team or player)", cmd_viz_shotmap,
        extras=lambda p: [
            p.add_argument("--team"),
            p.add_argument("--player"),
            p.add_argument("--half", choices=["attack", "defence"], default="attack"),
        ])

    _vz("heatmap", "xG density heatmap", cmd_viz_heatmap,
        extras=lambda p: [p.add_argument("--team")])

    _vz("europe", "Top players across Europe", cmd_viz_europe, league=False,
        extras=lambda p: [
            p.add_argument("--metric", default="xg_p90"),
            p.add_argument("--label", help="Axis label"),
            p.add_argument("--position", help="Position filter: FW, MF, DF"),
            p.add_argument("--top-n", type=int, default=20),
        ])

    _vz("league-radar", "League style radar chart", cmd_viz_league_radar, league=False)

    _vz("violin", "Cross-league stat distribution", cmd_viz_violin, league=False,
        extras=lambda p: [
            p.add_argument("--metric", default="xg_p90"),
            p.add_argument("--label", help="Axis label"),
        ])

    _vz("xg-leagues", "Goals vs xG by league", cmd_viz_xg_leagues, league=False)

    return parser


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = build_parser()
    args   = parser.parse_args()

    # Attach season to args if not already there (subparsers don't inherit it)
    if not hasattr(args, "season") or args.season is None:
        args.season = CURRENT_SEASON

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}")
        if "--debug" in sys.argv:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
