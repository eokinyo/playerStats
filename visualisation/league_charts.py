"""
visualisation/league_charts.py
Cross-league comparison charts — the ones that answer questions like
"which league presses hardest?" or "who are the best creators in Europe?"

These charts pull from multiple league databases via analysis.league_stats
and always carry a league label on every data point — no mixing.

Charts produced:
  - League xG comparison bar chart
  - Pressing intensity comparison
  - Top players across Europe (any metric)
  - League style radar
  - Stat distribution violin plots (how spread is a metric across leagues?)
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
from matplotlib.lines import Line2D

from config import league_paths, CURRENT_SEASON, LEAGUES
from analysis.league_stats import (
    league_xg_comparison,
    league_pressing_comparison,
    league_goals_vs_xg,
    top_players_across_leagues,
    league_stat_distribution,
    league_profile_radar,
)

logger = logging.getLogger(__name__)

# ── Design tokens ──────────────────────────────────────────────────────────────
BG     = "#0d1117"
FG     = "#e6edf3"
MUTED  = "#8b949e"
GRID   = "#21262d"
ACCENT = "#00ff87"
AMBER  = "#f5a623"
RED    = "#ff6b6b"
BLUE   = "#58a6ff"

# One consistent colour per league — used across all cross-league charts
LEAGUE_COLOURS = {
    "Premier League": "#38003c",
    "La Liga":        "#ee8707",
    "Bundesliga":     "#d3010c",
    "Serie A":        "#1a56db",
    "Ligue 1":        "#dba111",
}
LEAGUE_ACCENT = {
    "Premier League": "#00ff87",
    "La Liga":        "#f5a623",
    "Bundesliga":     "#ff6b6b",
    "Serie A":        "#58a6ff",
    "Ligue 1":        "#f0c040",
}


def _apply_dark_theme(fig, ax_or_axes):
    fig.patch.set_facecolor(BG)
    axes = ax_or_axes if isinstance(ax_or_axes, (list, np.ndarray)) else [ax_or_axes]
    for ax in np.array(axes).flatten():
        ax.set_facecolor(BG)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.xaxis.label.set_color(MUTED)
        ax.yaxis.label.set_color(MUTED)
        for spine in ax.spines.values():
            spine.set_color(GRID)


def _cross_league_save(fig: plt.Figure, filename: str) -> Path:
    """Saves cross-league charts to output/cross_league/charts/."""
    charts_dir = league_paths("cross_league")["charts"]
    charts_dir.mkdir(parents=True, exist_ok=True)
    path = charts_dir / filename
    fig.savefig(path, dpi=300, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    logger.info(f"Saved cross-league chart: {path}")
    return path


# ── xG comparison ─────────────────────────────────────────────────────────────

def xg_comparison_bar(
    season: str = CURRENT_SEASON,
    save: bool = True,
) -> plt.Figure:
    """
    Grouped bar chart comparing average xG and xGA per match across leagues.
    Shows which leagues produce the most open, chance-rich football.
    """
    df = league_xg_comparison(season)
    if df.empty:
        raise ValueError("No cross-league xG data available.")

    df = df.sort_values("avg_xg_per_match", ascending=False)

    x      = np.arange(len(df))
    width  = 0.35
    colors = [LEAGUE_ACCENT.get(l, ACCENT) for l in df["league"]]

    fig, ax = plt.subplots(figsize=(11, 6))
    _apply_dark_theme(fig, ax)

    bars_xg  = ax.bar(x - width / 2, df["avg_xg_per_match"],
                      width, color=colors, alpha=0.9,
                      edgecolor=BG, label="xG For")
    bars_xga = ax.bar(x + width / 2, df["avg_xga_per_match"],
                      width, color=colors, alpha=0.4,
                      edgecolor=BG, hatch="//", label="xGA Against")

    for bar in bars_xg:
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{bar.get_height():.2f}",
                ha="center", va="bottom", color=FG, fontsize=8)
    for bar in bars_xga:
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{bar.get_height():.2f}",
                ha="center", va="bottom", color=MUTED, fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(df["league"], color=FG, fontsize=9)
    ax.set_ylabel("Average xG per Match", color=MUTED, fontsize=10)
    ax.grid(axis="y", color=GRID, lw=0.4)
    ax.set_axisbelow(True)
    ax.set_ylim(0, df["avg_xg_per_match"].max() * 1.2)
    ax.legend(frameon=False, labelcolor=FG, fontsize=9)

    fig.text(0.12, 0.96, "xG per Match — Top 5 Leagues Compared",
             color=FG, fontsize=14, fontweight="bold")
    fig.text(0.12, 0.92, f"Season {season}  ·  average per team per match",
             color=MUTED, fontsize=9)
    fig.text(0.98, 0.02, "Data: Understat / FBref",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    if save:
        _cross_league_save(fig, f"xg_comparison_{season}.png")
    return fig


# ── Pressing comparison ────────────────────────────────────────────────────────

def pressing_comparison_bar(
    season: str = CURRENT_SEASON,
    save: bool = True,
) -> plt.Figure:
    """
    Horizontal bar chart: median PPDA per league.
    Includes a min-max range band to show spread within each league.
    """
    df = league_pressing_comparison(season)
    if df.empty:
        raise ValueError("No pressing data available.")

    df = df.sort_values("median_ppda", ascending=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    _apply_dark_theme(fig, ax)

    y      = np.arange(len(df))
    colors = [LEAGUE_ACCENT.get(l, ACCENT) for l in df["league"]]

    for i, (_, row) in enumerate(df.iterrows()):
        ax.plot([row["min_ppda"], row["max_ppda"]], [i, i],
                color=MUTED, lw=6, alpha=0.2, solid_capstyle="round")

    bars = ax.barh(y, df["median_ppda"], height=0.4,
                   color=colors, edgecolor=BG, alpha=0.9)

    for bar, val in zip(bars, df["median_ppda"]):
        ax.text(bar.get_width() + 0.1,
                bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", color=FG,
                fontsize=9, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(df["league"], color=FG, fontsize=10)
    ax.set_xlabel("← More Pressing   Median PPDA   Less Pressing →",
                  color=MUTED, fontsize=9)
    ax.grid(axis="x", color=GRID, lw=0.4)
    ax.set_axisbelow(True)

    range_patch = mpatches.Patch(color=MUTED, alpha=0.3, label="Min–Max range")
    ax.legend(handles=[range_patch], frameon=False, labelcolor=FG, fontsize=8)

    fig.text(0.12, 0.97, "Press Intensity — Top 5 Leagues",
             color=FG, fontsize=14, fontweight="bold")
    fig.text(0.12, 0.92,
             f"Season {season}  ·  PPDA: passes allowed per defensive action  ·  lower = more intense",
             color=MUTED, fontsize=8)
    fig.text(0.98, 0.02, "Data: Understat",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    if save:
        _cross_league_save(fig, f"pressing_comparison_{season}.png")
    return fig


# ── Top players across Europe ──────────────────────────────────────────────────

def european_ranking_bars(
    season: str = CURRENT_SEASON,
    metric: str = "xg_p90",
    metric_label: str = "xG per 90",
    top_n: int = 20,
    min_minutes: int = 900,
    position_group: str | None = None,
    save: bool = True,
) -> plt.Figure:
    """
    Horizontal bar chart of the top N players in Europe for any metric.
    Bars are coloured by league so you can instantly see distribution
    across competitions.

    Args:
        metric:         Any numeric player_stats column, e.g. "xg_p90",
                        "sca_p90", "progressive_carries", "gca_p90"
        metric_label:   Human-readable axis label.
        position_group: Optional FBref position filter — "FW", "MF", "DF"
        min_minutes:    900 default (10 full games) for cross-league fairness.
    """
    df = top_players_across_leagues(
        season, metric=metric, top_n=top_n,
        min_minutes=min_minutes, position_group=position_group,
    )
    if df.empty:
        raise ValueError(f"No cross-league data for metric '{metric}'")

    df     = df.sort_values(metric, ascending=True)
    colors = [LEAGUE_ACCENT.get(l, ACCENT) for l in df["league"]]
    labels = [f"{p}  ·  {t}" for p, t in zip(df["player"], df["team"])]

    fig, ax = plt.subplots(figsize=(11, max(7, len(df) * 0.48)))
    _apply_dark_theme(fig, ax)

    bars = ax.barh(labels, df[metric], color=colors,
                   height=0.7, edgecolor=BG, alpha=0.9)

    for bar, (_, row) in zip(bars, df.iterrows()):
        ax.text(bar.get_width() + df[metric].max() * 0.01,
                bar.get_y() + bar.get_height() / 2,
                f"{row[metric]:.2f}",
                va="center", color=FG, fontsize=8)
        ax.text(0.05, bar.get_y() + bar.get_height() / 2,
                row["league"][:3].upper(),
                va="center", color=BG, fontsize=6.5,
                fontweight="bold", alpha=0.9)

    ax.set_xlabel(metric_label, color=MUTED, fontsize=10)
    ax.set_xlim(0, df[metric].max() * 1.15)
    ax.grid(axis="x", color=GRID, lw=0.4)
    ax.set_axisbelow(True)

    legend_patches = [
        mpatches.Patch(color=LEAGUE_ACCENT.get(l, ACCENT), label=l)
        for l in df["league"].unique()
    ]
    ax.legend(handles=legend_patches, frameon=False, labelcolor=FG,
              fontsize=8, loc="lower right")

    pos_tag = f" — {position_group}s" if position_group else ""
    fig.text(0.12, 0.97, f"Top {top_n} in Europe — {metric_label}{pos_tag}",
             color=FG, fontsize=13, fontweight="bold")
    fig.text(0.12, 0.93,
             f"Season {season}  ·  min. {min_minutes} minutes played",
             color=MUTED, fontsize=8)
    fig.text(0.98, 0.01, "Data: FBref",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    if save:
        pos_str = f"_{position_group}" if position_group else ""
        _cross_league_save(fig, f"europe_top_{metric}{pos_str}_{season}.png")
    return fig


# ── League style radar ─────────────────────────────────────────────────────────

def league_style_radar(
    season: str = CURRENT_SEASON,
    save: bool = True,
) -> plt.Figure:
    """
    Radar / spider chart comparing all five leagues across six style dimensions:
      Chance Quality, Goals, Progressive Play,
      Shot Volume, Defensive Activity, Press Intensity

    Each axis is normalised 0-1 across the five leagues so they can be
    compared despite having different raw scales.
    """
    df = league_profile_radar(season)
    if df.empty:
        raise ValueError("No league radar data available.")

    metrics = [c for c in df.columns if c != "league"]
    N       = len(metrics)
    angles  = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    for r in [0.25, 0.5, 0.75, 1.0]:
        ax.plot(angles, [r] * (N + 1), color=GRID, lw=0.5, zorder=1)
        ax.text(angles[1], r + 0.03, f"{int(r*100)}",
                color=MUTED, fontsize=7, ha="left")

    for angle in angles[:-1]:
        ax.plot([angle, angle], [0, 1], color=GRID, lw=0.5, zorder=1)

    for _, row in df.iterrows():
        league  = row["league"]
        values  = row[metrics].tolist()
        values += values[:1]
        color   = LEAGUE_ACCENT.get(league, ACCENT)

        ax.plot(angles, values, color=color, lw=2, zorder=3, label=league)
        ax.fill(angles, values, color=color, alpha=0.08, zorder=2)
        ax.scatter(angles[:-1], row[metrics].tolist(),
                   color=color, s=35, zorder=4,
                   edgecolors=BG, lw=1.2)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, color=FG, fontsize=9, fontweight="bold")
    ax.set_yticks([])
    ax.set_ylim(0, 1)
    ax.spines["polar"].set_color(GRID)

    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.14),
              ncol=3, frameon=False, labelcolor=FG, fontsize=9)

    fig.text(0.5, 0.97, "League Style Profile — Top 5 Leagues",
             ha="center", color=FG, fontsize=14, fontweight="bold")
    fig.text(0.5, 0.93,
             f"Season {season}  ·  all axes normalised 0–1 within this season",
             ha="center", color=MUTED, fontsize=8)
    fig.text(0.98, 0.01, "Data: FBref / Understat",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout()
    if save:
        _cross_league_save(fig, f"league_style_radar_{season}.png")
    return fig


# ── Stat distribution violin plot ─────────────────────────────────────────────

def stat_distribution_violin(
    season: str = CURRENT_SEASON,
    metric: str = "xg_p90",
    metric_label: str = "xG per 90",
    min_minutes: int = 450,
    save: bool = True,
) -> plt.Figure:
    """
    Violin plot showing the distribution of a player metric across all five leagues.
    Reveals not just averages but the spread and shape of each league's talent pool.

    A wide violin  = large variation between players.
    A tall violin  = high ceiling (elite outliers present).
    A fat middle   = many players clustered near the median.
    """
    df = league_stat_distribution(season, metric=metric, min_minutes=min_minutes)
    if df.empty:
        raise ValueError(f"No distribution data for '{metric}'")

    league_order = list(LEAGUES.keys())
    league_data  = [df[df["league"] == l][metric].dropna().tolist()
                    for l in league_order if l in df["league"].unique()]
    league_names = [l for l in league_order if l in df["league"].unique()]
    colors       = [LEAGUE_ACCENT.get(l, ACCENT) for l in league_names]

    fig, ax = plt.subplots(figsize=(12, 6))
    _apply_dark_theme(fig, ax)

    parts = ax.violinplot(
        league_data,
        positions=range(len(league_names)),
        widths=0.7,
        showmedians=True,
        showextrema=False,
    )

    for pc, color in zip(parts["bodies"], colors):
        pc.set_facecolor(color)
        pc.set_alpha(0.3)
        pc.set_edgecolor(color)
        pc.set_linewidth(1.5)

    parts["cmedians"].set_colors(FG)
    parts["cmedians"].set_linewidth(2)

    for i, (data, color) in enumerate(zip(league_data, colors)):
        jitter = np.random.uniform(-0.08, 0.08, size=len(data))
        ax.scatter(
            np.full(len(data), i) + jitter, data,
            color=color, alpha=0.25, s=8, zorder=3, edgecolors="none",
        )

    for i, data in enumerate(league_data):
        median = np.median(data)
        ax.text(i, median + ax.get_ylim()[1] * 0.01,
                f"{median:.2f}", ha="center", va="bottom",
                color=FG, fontsize=8, fontweight="bold")

    ax.set_xticks(range(len(league_names)))
    ax.set_xticklabels(league_names, color=FG, fontsize=9)
    ax.set_ylabel(metric_label, color=MUTED, fontsize=10)
    ax.grid(axis="y", color=GRID, lw=0.4)
    ax.set_axisbelow(True)

    fig.text(0.12, 0.96,
             f"{metric_label} Distribution — Top 5 Leagues",
             color=FG, fontsize=14, fontweight="bold")
    fig.text(0.12, 0.92,
             f"Season {season}  ·  min. {min_minutes} mins  ·  "
             f"line = median  ·  dots = individual players",
             color=MUTED, fontsize=8)
    fig.text(0.98, 0.02, "Data: FBref",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout(rect=[0, 0, 1, 0.91])
    if save:
        _cross_league_save(fig, f"distribution_{metric}_{season}.png")
    return fig


# ── Goals vs xG by league ─────────────────────────────────────────────────────

def goals_vs_xg_by_league(
    season: str = CURRENT_SEASON,
    save: bool = True,
) -> plt.Figure:
    """
    Bar chart comparing total goals vs total xG per league.
    A positive delta means teams in that league collectively score more
    than expected — revealing finishing quality or weak goalkeeping at scale.
    """
    df = league_goals_vs_xg(season)
    if df.empty:
        raise ValueError("No goals vs xG data available.")

    df = df.sort_values("total_xg", ascending=False)
    x      = np.arange(len(df))
    width  = 0.35
    colors = [LEAGUE_ACCENT.get(l, ACCENT) for l in df["league"]]

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 8),
        gridspec_kw={"height_ratios": [3, 1]},
    )
    _apply_dark_theme(fig, [ax1, ax2])

    ax1.bar(x - width / 2, df["total_goals"], width,
            color=colors, alpha=0.9, edgecolor=BG, label="Actual Goals")
    ax1.bar(x + width / 2, df["total_xg"], width,
            color=colors, alpha=0.35, edgecolor=BG,
            hatch="//", label="Expected Goals (xG)")

    ax1.set_xticks(x)
    ax1.set_xticklabels(df["league"], color=FG, fontsize=9)
    ax1.set_ylabel("Season Total", color=MUTED, fontsize=9)
    ax1.grid(axis="y", color=GRID, lw=0.4)
    ax1.set_axisbelow(True)
    ax1.legend(frameon=False, labelcolor=FG, fontsize=8)

    bar_colors = [ACCENT if v >= 0 else RED for v in df["total_goals_vs_xg"]]
    ax2.bar(x, df["total_goals_vs_xg"], color=bar_colors,
            alpha=0.85, edgecolor=BG, width=0.5)
    ax2.axhline(0, color=MUTED, lw=0.8, linestyle="--")
    ax2.set_xticks(x)
    ax2.set_xticklabels(df["league"], color=FG, fontsize=9)
    ax2.set_ylabel("G − xG", color=MUTED, fontsize=9)
    ax2.grid(axis="y", color=GRID, lw=0.4)
    ax2.set_axisbelow(True)

    for i, (_, row) in enumerate(df.iterrows()):
        val = row["total_goals_vs_xg"]
        ax2.text(i, val + (2 if val >= 0 else -4),
                 f"{val:+.0f}", ha="center",
                 color=ACCENT if val >= 0 else RED,
                 fontsize=8, fontweight="bold")

    fig.text(0.12, 0.97, "Goals vs xG — Top 5 Leagues",
             color=FG, fontsize=14, fontweight="bold")
    fig.text(0.12, 0.93,
             f"Season {season}  ·  positive G−xG = overperforming "
             f"(clinical finishing / poor GKs)",
             color=MUTED, fontsize=8)
    fig.text(0.98, 0.01, "Data: Understat / FBref",
             color=MUTED, fontsize=7, ha="right")

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    if save:
        _cross_league_save(fig, f"goals_vs_xg_leagues_{season}.png")
    return fig
