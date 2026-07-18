"""
visualisation/shot_maps.py
Shot maps drawn on a pitch using mplsoccer.
Circle size = xG value. Colour = outcome (goal/saved/missed/blocked).
Includes team shot map, player shot map, and xG flow chart.
"""

import logging
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

try:
    from mplsoccer import Pitch, VerticalPitch
    MPLSOCCER_AVAILABLE = True
except ImportError:
    MPLSOCCER_AVAILABLE = False

from config import league_paths, CURRENT_SEASON
from storage.db import get_shots, query

logger = logging.getLogger(__name__)

BG       = "#0d1117"
BG_PANEL = "#161b22"
TEXT_PRI = "#e6edf3"
TEXT_SEC = "#8b949e"
ACCENT   = "#00ff85"
AMBER    = "#f0b429"
GRID     = "#21262d"

OUTCOME_COLORS = {
    "goal":         ACCENT,
    "savedshot":    AMBER,
    "missedshots":  "#4d6080",
    "blockedshot":  "#334466",
}


def _check():
    if not MPLSOCCER_AVAILABLE:
        raise ImportError("Run: pip install mplsoccer")


def _save(fig, league_name, filename):
    paths    = league_paths(league_name)
    out_path = paths["charts"] / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    logger.info(f"Saved: {out_path}")
    return out_path


def _color(result):
    if not isinstance(result, str):
        return TEXT_SEC
    return OUTCOME_COLORS.get(result.lower().replace(" ", ""), TEXT_SEC)


def team_shot_map(team, league_name, season=CURRENT_SEASON,
                  half="attack", save=True):
    """
    All shots taken (half='attack') or conceded (half='defence') by a team.
    Circle size = xG. Green star = Goal, Amber = Saved, Dark = Missed/Blocked.
    """
    _check()
    shots = get_shots(league_name, season, team=team)
    if shots.empty:
        logger.warning(f"No shot data for {team}")
        return None

    if half == "defence":
        all_shots = get_shots(league_name, season)
        shots     = all_shots[all_shots["team"] != team].copy()
        shots["x"] = 105 - shots["x"]
        shots["y"] = 68  - shots["y"]

    shots = shots.dropna(subset=["x", "y", "xg"])

    fig, ax = plt.subplots(figsize=(13, 9), facecolor=BG)
    pitch   = Pitch(pitch_type="custom", pitch_length=105, pitch_width=68,
                    pitch_color=BG_PANEL, line_color=GRID,
                    linewidth=1.2, goal_type="box")
    pitch.draw(ax=ax)

    sizes     = (shots["xg"].clip(0.01, 1.0) * 400).clip(20, 400)
    mask_goal = shots["result"].str.lower() == "goal"

    ax.scatter(shots.loc[~mask_goal, "x"], shots.loc[~mask_goal, "y"],
               s=sizes[~mask_goal],
               c=shots.loc[~mask_goal, "result"].apply(_color),
               alpha=0.55, edgecolors=BG, linewidths=0.4, zorder=3)
    ax.scatter(shots.loc[mask_goal, "x"], shots.loc[mask_goal, "y"],
               s=sizes[mask_goal], c=ACCENT, alpha=0.95,
               edgecolors=BG, linewidths=0.7, marker="*", zorder=4)

    total_xg = shots["xg"].sum()
    ax.text(2, 66,
            f"Shots: {len(shots)}   Goals: {mask_goal.sum()}   "
            f"xG: {total_xg:.1f}   Avg xG/shot: {shots['xg'].mean():.3f}",
            color=TEXT_SEC, fontsize=9, va="top", family="monospace")

    ax.legend(handles=[
        mpatches.Patch(color=ACCENT,    label="Goal ★"),
        mpatches.Patch(color=AMBER,     label="Saved"),
        mpatches.Patch(color="#4d6080", label="Missed / Blocked"),
    ], loc="upper right", facecolor=BG_PANEL, edgecolor=GRID,
       labelcolor=TEXT_PRI, fontsize=9)

    direction = "Shots Taken" if half == "attack" else "Shots Conceded"
    ax.set_title(f"{team} — {direction}\n{league_name} · {season}",
                 color=TEXT_PRI, fontsize=13, fontweight="bold", pad=12)

    if save:
        safe = team.replace(" ", "_").lower()
        _save(fig, league_name,
              f"shotmap_{safe}_{'attack' if half == 'attack' else 'defence'}_{season}.png")
    return fig


def player_shot_map(player, league_name, season=CURRENT_SEASON, save=True):
    """
    Shot map for a single player — all shots across the season.
    Uses a vertical half-pitch (attacking third) for clarity.
    """
    _check()
    shots = get_shots(league_name, season, player=player)
    if shots.empty:
        logger.warning(f"No shot data for {player}")
        return None
    shots = shots.dropna(subset=["x", "y", "xg"])

    fig, ax = plt.subplots(figsize=(10, 10), facecolor=BG)
    pitch   = VerticalPitch(pitch_type="custom", pitch_length=105, pitch_width=68,
                            pitch_color=BG_PANEL, line_color=GRID,
                            linewidth=1.2, half=True, goal_type="box")
    pitch.draw(ax=ax)

    sizes     = (shots["xg"].clip(0.01, 1.0) * 500).clip(30, 500)
    mask_goal = shots["result"].str.lower() == "goal"

    ax.scatter(shots.loc[~mask_goal, "y"], shots.loc[~mask_goal, "x"],
               s=sizes[~mask_goal],
               c=shots.loc[~mask_goal, "result"].apply(_color),
               alpha=0.6, edgecolors=BG, linewidths=0.4, zorder=3)
    ax.scatter(shots.loc[mask_goal, "y"], shots.loc[mask_goal, "x"],
               s=sizes[mask_goal] * 1.3, c=ACCENT, alpha=0.95,
               edgecolors="white", linewidths=0.8, marker="*", zorder=4)

    goals     = mask_goal.sum()
    total_xg  = shots["xg"].sum()
    delta     = goals - total_xg
    sign      = "+" if delta >= 0 else ""

    ax.set_title(
        f"{player}\n"
        f"{len(shots)} shots · {int(goals)} goals · "
        f"{total_xg:.1f} xG · {sign}{delta:.1f} G−xG\n"
        f"{league_name} · {season}",
        color=TEXT_PRI, fontsize=12, fontweight="bold", pad=12,
    )
    ax.legend(handles=[
        mpatches.Patch(color=ACCENT,    label="Goal ★"),
        mpatches.Patch(color=AMBER,     label="Saved"),
        mpatches.Patch(color="#4d6080", label="Missed / Blocked"),
    ], loc="lower right", facecolor=BG_PANEL, edgecolor=GRID,
       labelcolor=TEXT_PRI, fontsize=9)

    if save:
        safe = player.replace(" ", "_").lower()
        _save(fig, league_name, f"shotmap_{safe}_{season}.png")
    return fig


def xg_flow_chart(match_id, home_team, away_team,
                  league_name, season=CURRENT_SEASON, save=True):
    """
    Cumulative xG over match time for both teams.
    Goals marked with vertical dotted lines and football emoji.
    Shows momentum — who was 'winning' on xG throughout the match.
    """
    from analysis.xg_analysis import xg_flow

    flow = xg_flow(league_name, season, match_id)
    if flow.empty:
        return None

    shot_sql = """
        SELECT minute, side, result FROM shot_events
        WHERE match_id=? AND league=? AND season=?
        ORDER BY minute
    """
    shots = query(shot_sql, league_name, params=(match_id, league_name, season))
    goals = shots[shots["result"].str.lower() == "goal"] \
            if not shots.empty else None

    fig, ax = plt.subplots(figsize=(13, 7), facecolor=BG)
    ax.set_facecolor(BG_PANEL)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)

    home_col = "home_xg_cumulative"
    away_col = "away_xg_cumulative"

    if home_col in flow.columns:
        ax.plot(flow["minute"], flow[home_col], color=ACCENT, lw=2.5,
                label=home_team, zorder=3)
        ax.fill_between(flow["minute"], flow[home_col],
                        alpha=0.12, color=ACCENT, zorder=2)

    if away_col in flow.columns:
        ax.plot(flow["minute"], flow[away_col], color=AMBER, lw=2.5,
                label=away_team, linestyle="--", zorder=3)
        ax.fill_between(flow["minute"], flow[away_col],
                        alpha=0.10, color=AMBER, zorder=2)

    if goals is not None and not goals.empty:
        ymax = max(
            flow[home_col].max() if home_col in flow.columns else 0,
            flow[away_col].max() if away_col in flow.columns else 0,
        ) * 0.97
        for _, g in goals.iterrows():
            c = ACCENT if g["side"] == "home" else AMBER
            ax.axvline(g["minute"], color=c, lw=1, alpha=0.45,
                       linestyle=":", zorder=1)
            ax.text(g["minute"], ymax, "⚽", ha="center",
                    fontsize=10, color=c, alpha=0.8)

    ax.axvline(45, color=TEXT_SEC, lw=0.8, linestyle="--", alpha=0.35)
    ax.text(45.5, 0.02, "HT", color=TEXT_SEC, fontsize=8, alpha=0.45)
    ax.set_xlim(0, 95)
    ax.set_xlabel("Minute", color=TEXT_SEC, fontsize=11)
    ax.set_ylabel("Cumulative xG", color=TEXT_SEC, fontsize=11)
    ax.set_title(
        f"{home_team} vs {away_team} — xG Flow\n{league_name} · {season}",
        color=TEXT_PRI, fontsize=13, fontweight="bold",
    )
    ax.tick_params(colors=TEXT_SEC)
    ax.grid(color=GRID, lw=0.5, zorder=1)
    ax.legend(facecolor=BG_PANEL, edgecolor=GRID,
              labelcolor=TEXT_PRI, fontsize=10)

    plt.tight_layout()
    if save:
        sh = home_team.replace(" ", "_").lower()
        sa = away_team.replace(" ", "_").lower()
        _save(fig, league_name, f"xgflow_{sh}_vs_{sa}_{season}.png")
    return fig
