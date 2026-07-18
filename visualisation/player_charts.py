"""
visualisation/player_charts.py
Player-level charts — radar profiles, scatter plots, and ranking bars.

Design language used throughout:
  - Dark background (#0d1117) with a pitch-green accent (#00ff85)
  - Primary text in off-white (#e6edf3), secondary in slate (#8b949e)
  - Amber (#f0b429) for comparison overlays, red (#ff4d4d) for underperformers
  - Minimal grid lines — data speaks, no chartjunk

All functions return the figure AND save to output/<league>/charts/.
"""

import logging
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from config import league_paths, CURRENT_SEASON
from analysis.player_stats import (
    player_percentile_profile,
    top_scorers,
    overperformers,
    underperformers,
    shot_creation_leaders,
    _col_missing,
)

logger = logging.getLogger(__name__)

# ── Design tokens ──────────────────────────────────────────────────────────────
BG       = "#0d1117"
BG_PANEL = "#161b22"
TEXT_PRI = "#e6edf3"
TEXT_SEC = "#8b949e"
ACCENT   = "#00ff85"
AMBER    = "#f0b429"
RED      = "#ff4d4d"
GRID     = "#21262d"

# Real club colours + standard 3-letter codes, same rationale as
# team_charts.py: identity via a small badge/bar tint, not actual crests
# (which would mean reproducing trademarked logos). Duplicated locally
# rather than cross-imported, matching this codebase's existing pattern
# of file-local helpers (see _col_missing in analysis/player_stats.py
# and analysis/team_stats.py).
PL_CLUB_COLORS = {
    "Arsenal":                 "#EF0107",
    "Aston Villa":             "#670E36",
    "Bournemouth":             "#DA020E",
    "Brentford":               "#C10000",
    "Brighton":                "#0057B7",
    "Chelsea":                 "#034694",
    "Crystal Palace":          "#0055A5",
    "Everton":                 "#003399",
    "Fulham":                  "#FFFFFF",
    "Ipswich":                 "#0044A9",
    "Leicester":               "#003090",
    "Liverpool":               "#C8102E",
    "Manchester City":         "#6CABDD",
    "Manchester United":       "#DA020E",
    "Newcastle United":        "#F0B83D",
    "Nottingham Forest":       "#DD0000",   # approximate
    "Southampton":             "#D71920",   # approximate
    "Tottenham":               "#132257",
    "West Ham":                "#7A263A",
    "Wolverhampton Wanderers": "#FDB913",
}
PL_CLUB_CODES = {
    "Arsenal": "ARS", "Aston Villa": "AVL", "Bournemouth": "BOU",
    "Brentford": "BRE", "Brighton": "BHA", "Chelsea": "CHE",
    "Crystal Palace": "CRY", "Everton": "EVE", "Fulham": "FUL",
    "Ipswich": "IPS", "Leicester": "LEI", "Liverpool": "LIV",
    "Manchester City": "MCI", "Manchester United": "MUN",
    "Newcastle United": "NEW", "Nottingham Forest": "NFO",
    "Southampton": "SOU", "Tottenham": "TOT", "West Ham": "WHU",
    "Wolverhampton Wanderers": "WOL",
}


def _text_color_for_bg(hex_color: str) -> str:
    """Picks black or white text based on background luminance."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.6 else "#FFFFFF"


def _save(fig: plt.Figure, league_name: str, filename: str) -> Path:
    paths    = league_paths(league_name)
    out_path = paths["charts"] / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    logger.info(f"Saved: {out_path}")
    return out_path


def _style_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(BG_PANEL)
    ax.tick_params(colors=TEXT_SEC, labelsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.xaxis.label.set_color(TEXT_SEC)
    ax.yaxis.label.set_color(TEXT_SEC)


# ── Radar / spider chart ───────────────────────────────────────────────────────

def radar_chart(
    player_name: str,
    league_name: str,
    season: str = CURRENT_SEASON,
    position_group: str | None = None,
    compare_player: str | None = None,
    save: bool = True,
) -> plt.Figure:
    """
    Radar/spider chart showing a player's percentile profile.
    Optionally overlays a second player for head-to-head comparison.

    Each axis = one metric (0 = worst in league, 100 = best).
    Filled area shows how the player ranks vs peers.

    Args:
        player_name:    Primary player (exact name as in database).
        compare_player: Optional second player to overlay in amber.
        position_group: "FW", "MF", "DF" — compares within position if set.
        save:           Save to output/<league>/charts/.
    """
    profile = player_percentile_profile(
        player_name, league_name, season, position_group=position_group
    )
    if profile.empty:
        logger.warning(f"No profile data for {player_name}")
        return None

    labels      = profile["label"].tolist()
    values      = profile["percentile"].tolist()
    n           = len(labels)
    angles      = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    values_plot = values + [values[0]]
    angles_plot = angles + [angles[0]]

    fig = plt.figure(figsize=(9, 9), facecolor=BG)
    ax  = fig.add_subplot(111, polar=True, facecolor=BG_PANEL)

    # Grid rings at 20/40/60/80/100
    for r in [20, 40, 60, 80, 100]:
        ax.plot(np.linspace(0, 2 * np.pi, 200), [r] * 200,
                color=GRID, lw=0.5, zorder=1)
        ax.text(np.pi / 2, r + 3, str(r), color=TEXT_SEC, fontsize=7,
                ha="center", va="bottom")

    # Spoke lines
    for angle in angles:
        ax.plot([angle, angle], [0, 100], color=GRID, lw=0.5, zorder=1)

    # Primary player — green fill
    ax.plot(angles_plot, values_plot, color=ACCENT, lw=2.5, zorder=3)
    ax.fill(angles_plot, values_plot, color=ACCENT, alpha=0.25, zorder=2)
    ax.scatter(angles, values, color=ACCENT, s=40, zorder=4)

    # Optional comparison player — amber dashed
    if compare_player:
        cmp_profile = player_percentile_profile(
            compare_player, league_name, season, position_group=position_group
        )
        if not cmp_profile.empty:
            cmp_vals  = cmp_profile["percentile"].tolist()
            cmp_plot  = cmp_vals + [cmp_vals[0]]
            ax.plot(angles_plot, cmp_plot, color=AMBER, lw=2.5,
                    linestyle="--", zorder=3)
            ax.fill(angles_plot, cmp_plot, color=AMBER, alpha=0.15, zorder=2)
            ax.scatter(angles, cmp_vals, color=AMBER, s=40, zorder=4)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, color=TEXT_PRI, fontsize=9, fontweight="bold")
    ax.set_yticks([])
    ax.set_ylim(0, 145)  # wide headroom above 100 so near-max data points don't crowd the axis labels
    ax.spines["polar"].set_color(GRID)

    # Title
    pos_note = f" · {position_group}s only" if position_group else ""
    cmp_note = f" vs {compare_player}" if compare_player else ""
    ax.set_title(
        f"{player_name}{cmp_note}\nPercentile Profile{pos_note}\n{league_name} · {season}",
        color=TEXT_PRI, fontsize=12, fontweight="bold", pad=25,
    )

    handles = [mpatches.Patch(color=ACCENT, alpha=0.7, label=player_name)]
    if compare_player:
        handles.append(mpatches.Patch(color=AMBER, alpha=0.7, label=compare_player))
    ax.legend(handles=handles, loc="upper right",
              bbox_to_anchor=(1.35, 1.15),
              facecolor=BG_PANEL, edgecolor=GRID,
              labelcolor=TEXT_PRI, fontsize=10)

    plt.tight_layout()
    if save:
        safe = player_name.replace(" ", "_").lower()
        _save(fig, league_name, f"radar_{safe}_{season}.png")
    return fig


# ── Scatter plots ──────────────────────────────────────────────────────────────

def xg_vs_goals_scatter(
    league_name: str,
    season: str = CURRENT_SEASON,
    min_minutes: int = 450,
    top_n: int = 80,
    save: bool = True,
) -> plt.Figure:
    """
    Scatter: xG (x-axis) vs actual goals (y-axis).
    Diagonal = perfect expectation. Above = overperformer, below = under.
    Top outliers labelled automatically.
    Green dots = beating xG. Red dots = missing xG.
    """
    df = top_scorers(league_name, season, top_n=top_n, min_minutes=min_minutes)
    if df.empty:
        return None

    if "goals_minus_xg" not in df.columns:
        df["goals_minus_xg"] = df["goals"] - df["xg"]

    fig, ax = plt.subplots(figsize=(11, 9), facecolor=BG)
    _style_ax(ax)

    colors = [ACCENT if v >= 0 else RED for v in df["goals_minus_xg"]]
    ax.scatter(df["xg"], df["goals"], c=colors, s=65, alpha=0.82,
               edgecolors=BG, linewidths=0.5, zorder=3)

    # Diagonal expectation line
    max_val = max(df["xg"].max(), df["goals"].max()) * 1.08
    ax.plot([0, max_val], [0, max_val], color=TEXT_SEC, lw=1.2,
            linestyle="--", alpha=0.5, zorder=2)
    ax.text(max_val * 0.6, max_val * 0.57, "goals = xG",
            color=TEXT_SEC, fontsize=8, alpha=0.6, rotation=38)

    # Label top 12 outliers by absolute overperformance
    top_outliers = df.reindex(
        df["goals_minus_xg"].abs().sort_values(ascending=False).index
    ).head(12)
    for _, row in top_outliers.iterrows():
        ax.annotate(
            row["player"].split()[-1],
            (row["xg"], row["goals"]),
            fontsize=7.5, color=TEXT_PRI, alpha=0.9,
            xytext=(5, 4), textcoords="offset points",
        )

    ax.set_xlabel("Expected Goals (xG)", fontsize=11)
    ax.set_ylabel("Actual Goals Scored", fontsize=11)
    ax.set_title(
        f"Goals vs xG — {league_name} · {season}",
        color=TEXT_PRI, fontsize=13, fontweight="bold",
    )
    ax.grid(color=GRID, lw=0.5, zorder=1)

    patches = [
        mpatches.Patch(color=ACCENT, label="Overperforming xG"),
        mpatches.Patch(color=RED,    label="Underperforming xG"),
    ]
    ax.legend(handles=patches, facecolor=BG_PANEL,
              edgecolor=GRID, labelcolor=TEXT_PRI, fontsize=9)

    plt.tight_layout()
    if save:
        _save(fig, league_name, f"xg_vs_goals_{season}.png")
    return fig


def sca_vs_xag_scatter(
    league_name: str,
    season: str = CURRENT_SEASON,
    min_minutes: int = 450,
    save: bool = True,
) -> plt.Figure:
    """
    Scatter: Shot-Creating Actions/90 vs xAG/90.
    Separates volume creators (high SCA) from quality creators (high xAG).
    Top-right quadrant = elite creators doing both.
    """
    from storage.db import get_players
    import pandas as pd

    sca_df = shot_creation_leaders(
        league_name, season, top_n=120, min_minutes=min_minutes
    )
    std_df = get_players(
        league_name, season, stat_type="standard", min_minutes=min_minutes
    )

    if sca_df.empty or std_df.empty:
        return None

    df = sca_df.merge(
        std_df[["player", "team", "xag", "minutes"]],
        on=["player", "team"], how="inner",
    )
    mins_col    = "minutes_x" if "minutes_x" in df.columns else "minutes"
    df["mins"]  = df[mins_col]
    df["xag_p90"] = (df["xag"] / df["mins"].replace(0, np.nan)) * 90

    if "sca_p90" not in df.columns or "xag_p90" not in df.columns:
        return None

    fig, ax = plt.subplots(figsize=(11, 9), facecolor=BG)
    _style_ax(ax)

    ax.scatter(df["sca_p90"], df["xag_p90"], color=ACCENT, s=55,
               alpha=0.75, edgecolors=BG, linewidths=0.4, zorder=3)

    # Median quadrant lines
    med_sca = df["sca_p90"].median()
    med_xag = df["xag_p90"].median()
    ax.axvline(med_sca, color=GRID, lw=1, linestyle="--", alpha=0.8)
    ax.axhline(med_xag, color=GRID, lw=1, linestyle="--", alpha=0.8)

    # Quadrant labels
    xmax = df["sca_p90"].max()
    ymax = df["xag_p90"].max()
    ax.text(xmax * 0.98, ymax * 0.97, "High SCA\nHigh xAG",
            color=ACCENT, fontsize=8, ha="right", va="top", alpha=0.75)
    ax.text(xmax * 0.02, ymax * 0.97, "Low SCA\nHigh xAG",
            color=AMBER, fontsize=8, ha="left", va="top", alpha=0.75)

    # Label top 10 by xAG
    for _, row in df.nlargest(10, "xag_p90").iterrows():
        ax.annotate(row["player"].split()[-1],
                    (row["sca_p90"], row["xag_p90"]),
                    fontsize=7.5, color=TEXT_PRI,
                    xytext=(4, 3), textcoords="offset points")

    ax.set_xlabel("Shot-Creating Actions per 90", fontsize=11)
    ax.set_ylabel("xAG per 90 (Expected Assisted Goals)", fontsize=11)
    ax.set_title(
        f"Chance Creation — Volume vs Quality\n{league_name} · {season}",
        color=TEXT_PRI, fontsize=13, fontweight="bold",
    )
    ax.grid(color=GRID, lw=0.5, zorder=1)
    plt.tight_layout()

    if save:
        _save(fig, league_name, f"sca_vs_xag_{season}.png")
    return fig


# ── Ranking bar charts ─────────────────────────────────────────────────────────

def ranking_bar(
    league_name: str,
    season: str = CURRENT_SEASON,
    metric: str = "goals",
    label: str = "Goals",
    top_n: int = 15,
    min_minutes: int = 450,
    stat_type: str = "standard",
    save: bool = True,
) -> plt.Figure:
    """
    Horizontal bar chart ranking top N players by any numeric metric.
    Works for goals, assists, xg, sca_p90, tackles_interceptions, etc.
    Bars use each player's real club colour (safe here, unlike the
    pressing chart — bar length alone already says "more is better",
    so colour is free to carry identity without competing signals), with
    a club-code badge for a quick read, and a dynamic headline calling
    out the leader's gap over second place.

    Args:
        metric:    Column name to rank by.
        label:     Human-readable axis label.
        stat_type: Which stat table to pull from ("standard", "shooting", etc.)
    """
    from storage.db import get_players
    df = get_players(league_name, season, stat_type=stat_type,
                     min_minutes=min_minutes)

    if df.empty or _col_missing(df, metric):
        logger.warning(f"Metric '{metric}' not available (or has no data) in {stat_type}")
        return None

    df = df.nlargest(top_n, metric)[["player", "team", metric]].reset_index(drop=True)
    df = df.sort_values(metric, ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, top_n * 0.55 + 2.8), facecolor=BG)
    _style_ax(ax)

    for i, row in df.iterrows():
        club_color = PL_CLUB_COLORS.get(row["team"], ACCENT)
        edge       = "#000000" if club_color == "#FFFFFF" else "none"
        bar = ax.barh(row["player"], row[metric],
                      color=club_color, edgecolor=edge, linewidth=1.0, height=0.68)
        code       = PL_CLUB_CODES.get(row["team"], row["team"][:3].upper())
        text_color = _text_color_for_bg(club_color)
        ax.text(df[metric].max() * 0.018, i, code,
                va="center", ha="left", color=text_color, fontsize=7.5, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.22", facecolor=club_color, edgecolor=edge))
        ax.text(
            row[metric] + df[metric].max() * 0.02,
            i,
            f"{row[metric]:.2g}",
            va="center", ha="left", color=TEXT_SEC, fontsize=8.5,
        )

    leader, second = df.iloc[-1], df.iloc[-2]
    gap = leader[metric] - second[metric]
    gap_str = f"{gap:.0f}" if float(gap).is_integer() else f"{gap:.1f}"

    ax.set_xlim(0, df[metric].max() * 1.28)
    ax.set_xlabel(label, fontsize=11)
    ax.tick_params(axis="y", labelcolor=TEXT_PRI, labelsize=9.5)
    ax.grid(axis="x", color=GRID, lw=0.5, zorder=1)
    ax.set_axisbelow(True)

    fig.suptitle(f"Top {top_n} by {label}", color=TEXT_PRI, fontsize=16,
                fontweight="bold", y=0.985)
    fig.text(0.5, 0.955,
            f"{leader['player']} leads the league by {gap_str} over {second['player']}",
            ha="center", color=ACCENT, fontsize=10.5, style="italic")
    fig.text(0.5, 0.935, f"{league_name} {season}",
            ha="center", color=TEXT_SEC, fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    if save:
        safe = metric.replace("/", "_").replace(" ", "_")
        _save(fig, league_name, f"ranking_{safe}_{season}.png")
    return fig


def overperformance_bar(
    league_name: str,
    season: str = CURRENT_SEASON,
    metric: str = "goals",
    top_n: int = 15,
    min_minutes: int = 450,
    save: bool = True,
) -> plt.Figure:
    """
    Diverging horizontal bar chart.
    Green bars = beating expectation. Red bars = missing expectation.
    Shows both the best over and worst underperformers in one view.
    """
    over  = overperformers(league_name, season, metric=metric,
                           top_n=top_n, min_minutes=min_minutes)
    under = underperformers(league_name, season, metric=metric,
                            top_n=top_n // 2, min_minutes=min_minutes)

    df = over._append(under).drop_duplicates(subset="player")
    df = df.sort_values("overperformance", ascending=True).reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(10, len(df) * 0.52 + 2), facecolor=BG)
    _style_ax(ax)

    colors = [ACCENT if v >= 0 else RED for v in df["overperformance"]]
    ax.barh(df["player"], df["overperformance"],
            color=colors, alpha=0.85, edgecolor="none", height=0.7)
    ax.axvline(0, color=TEXT_SEC, lw=1.2)

    for _, row in df.iterrows():
        v    = row["overperformance"]
        sign = "+" if v >= 0 else ""
        ax.text(
            v + (df["overperformance"].abs().max() * (0.015 if v >= 0 else -0.015)),
            df[df["player"] == row["player"]].index[0],
            f"{sign}{v:.2f}",
            va="center", ha="left" if v >= 0 else "right",
            color=TEXT_PRI, fontsize=8.2,
        )

    metric_word = "Goals" if metric == "goals" else "Assists"
    ax.set_xlabel(f"{metric_word} minus Expected", fontsize=11)
    ax.set_title(
        f"{metric_word} Overperformance (Actual − xG)\n{league_name} · {season}",
        color=TEXT_PRI, fontsize=13, fontweight="bold",
    )
    ax.tick_params(axis="y", labelcolor=TEXT_PRI, labelsize=9)
    ax.grid(axis="x", color=GRID, lw=0.5, zorder=1)
    ax.set_axisbelow(True)

    plt.tight_layout()
    if save:
        _save(fig, league_name, f"overperformance_{metric}_{season}.png")
    return fig
