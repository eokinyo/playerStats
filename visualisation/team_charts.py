"""
visualisation/team_charts.py
Team-level charts: attack vs defence scatter, pressing bar,
form trend, and xG league table.
"""
import logging
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
from adjustText import adjust_text

from config import league_paths, CURRENT_SEASON
from analysis.team_stats import (
    league_table, attack_profiles, defence_profiles,
    pressing_rankings, team_form,
)

logger = logging.getLogger(__name__)

BG       = "#0d1117"
BG_PANEL = "#161b22"
TEXT_PRI = "#e6edf3"
TEXT_SEC = "#8b949e"
ACCENT   = "#00ff85"
AMBER    = "#f0b429"
RED      = "#ff4d4d"
GRID     = "#21262d"

# Real Premier League club colours — used only for the small identity
# badge on each bar now, not the bar itself (see pressing_bar). A couple
# (marked below) are best-effort approximations rather than pixel-verified
# official brand hex — fine for a chart accent, worth a proper check if
# exact brand accuracy ever matters. Newcastle uses their gold accent
# instead of literal black/white, since neither renders visibly on badges.
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

# Standard 3-letter club codes (same ones used on Sky Sports / FPL) — used
# on the identity badge in place of an actual crest, which would mean
# reproducing trademarked club logos.
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
    """Picks black or white text based on background luminance, so a badge
    stays readable whether the club colour behind it is light or dark."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000000" if luminance > 0.6 else "#FFFFFF"


def _save(fig, league_name, filename):
    paths    = league_paths(league_name)
    out_path = paths["charts"] / filename
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    logger.info(f"Saved: {out_path}")
    return out_path


def _style_ax(ax):
    ax.set_facecolor(BG_PANEL)
    ax.tick_params(colors=TEXT_SEC, labelsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID)
    ax.xaxis.label.set_color(TEXT_SEC)
    ax.yaxis.label.set_color(TEXT_SEC)


def attack_vs_defence_scatter(league_name, season=CURRENT_SEASON, save=True):
    """
    Each team plotted by xG/match (attack, x-axis) vs xGA/match (defence,
    y-axis, inverted so "better" is toward the top). Club-colour badges
    mark each team's position instead of a scatter dot + separate label —
    more compact, and gives instant identity without a colorbar to decode.
    The four quadrants are shaded and labelled in plain English, so
    reading the chart doesn't depend on knowing what "top-right" means
    in xG terms.
    """
    attack  = attack_profiles(league_name, season)
    defence = defence_profiles(league_name, season)
    if attack.empty or defence.empty:
        return None

    df = attack.merge(defence[["team", "xga", "xga_per_match"]],
                      on="team", how="inner")
    if "xg_per_match" not in df.columns:
        df["xg_per_match"] = df["xg"] / 38
    if "xga_per_match" not in df.columns:
        df["xga_per_match"] = df["xga"] / 38
    df["xg_diff"] = df["xg_per_match"] - df["xga_per_match"]

    fig, ax = plt.subplots(figsize=(12, 10), facecolor=BG)
    _style_ax(ax)

    med_x = df["xg_per_match"].median()
    med_y = df["xga_per_match"].median()

    # Plot invisibly first so matplotlib autoscales to the data, then read
    # back the limits to size the quadrant backgrounds exactly to fit.
    ax.scatter(df["xg_per_match"], df["xga_per_match"], alpha=0)
    ax.invert_yaxis()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()   # after inversion, y1 < y0 (top of chart = smaller xGA = better)

    # Quadrant backgrounds — defined in data space; inverting the y-axis
    # only changes where these land on screen, not how they're built here.
    quad_style = dict(zorder=0, linewidth=0, alpha=0.10)
    ax.add_patch(plt.Rectangle((med_x, y1), x1 - med_x, med_y - y1,
                               facecolor=ACCENT, **quad_style))     # top-right
    ax.add_patch(plt.Rectangle((x0, y1), med_x - x0, med_y - y1,
                               facecolor=TEXT_SEC, **quad_style))   # top-left
    ax.add_patch(plt.Rectangle((med_x, med_y), x1 - med_x, y0 - med_y,
                               facecolor=AMBER, **quad_style))      # bottom-right
    ax.add_patch(plt.Rectangle((x0, med_y), med_x - x0, y0 - med_y,
                               facecolor=RED, **quad_style))        # bottom-left

    label_style = dict(fontsize=13, fontweight="bold", alpha=0.35, zorder=1, ha="center", va="center")
    ax.text((med_x + x1) / 2, (y1 + med_y) / 2, "ELITE", color=ACCENT, **label_style)
    ax.text((x0 + med_x) / 2, (y1 + med_y) / 2, "STURDY,\nBLUNT UP FRONT", color=TEXT_SEC, **label_style)
    ax.text((med_x + x1) / 2, (med_y + y0) / 2, "THRILLING,\nBUT LEAKY", color=AMBER, **label_style)
    ax.text((x0 + med_x) / 2, (med_y + y0) / 2, "STRUGGLING", color=RED, **label_style)

    ax.axvline(med_x, color=GRID, lw=1, linestyle="--", alpha=0.5, zorder=1)
    ax.axhline(med_y, color=GRID, lw=1, linestyle="--", alpha=0.5, zorder=1)

    # Club badges mark each team's position. A few teams cluster tightly
    # (e.g. Man City/Chelsea/Newcastle/Bournemouth this season) so badges
    # alone would overlap illegibly — a small precise dot marks the true
    # position, and adjustText nudges the badge apart with a thin
    # connector line back to its dot wherever it had to move.
    texts = []
    for _, row in df.iterrows():
        club_color = PL_CLUB_COLORS.get(row["team"], ACCENT)
        text_color = _text_color_for_bg(club_color)
        code       = PL_CLUB_CODES.get(row["team"], row["team"][:3].upper())
        ax.scatter([row["xg_per_match"]], [row["xga_per_match"]],
                  color=club_color, s=35, edgecolors=BG, linewidths=0.6, zorder=4)
        t = ax.text(row["xg_per_match"], row["xga_per_match"], code,
                    ha="center", va="center", fontsize=7.5, fontweight="bold",
                    color=text_color, zorder=5,
                    bbox=dict(boxstyle="round,pad=0.22", facecolor=club_color, edgecolor="none"))
        texts.append(t)

    adjust_text(texts, ax=ax,
               arrowprops=dict(arrowstyle="-", color=GRID, lw=0.7, alpha=0.8),
               expand=(1.3, 1.5), force_text=(0.3, 0.4))

    best  = df.loc[df["xg_diff"].idxmax()]
    worst = df.loc[df["xg_diff"].idxmin()]

    ax.set_xlabel("xG per Match (Attack)", fontsize=11)
    ax.set_ylabel("xGA per Match (Defence — lower is better)", fontsize=11)
    ax.grid(color=GRID, lw=0.5, zorder=0.5)
    ax.set_axisbelow(True)

    fig.suptitle("Attack vs Defence — Who's Actually Elite?", color=TEXT_PRI,
                fontsize=16, fontweight="bold", y=0.985)
    fig.text(0.5, 0.955,
            f"{best['team']} do it at both ends — {worst['team']} are exposed everywhere",
            ha="center", color=ACCENT, fontsize=10.5, style="italic")
    fig.text(0.5, 0.935,
            f"{league_name} {season}  ·  each badge is a team's actual position",
            ha="center", color=TEXT_SEC, fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    if save:
        _save(fig, league_name, f"attack_vs_defence_{season}.png")
    return fig


def pressing_bar(league_name, season=CURRENT_SEASON, save=True):
    """
    Teams ranked by PPDA (lower = more press). The bar colour is a
    green-to-red performance gradient (green = intense press, red =
    passive); a small club-colour badge with the standard 3-letter code
    sits near the start of each bar for identity, since embedding actual
    club crests would mean reproducing trademarked logos. Leads with a
    plain-language headline and calls out the standout team directly.
    """
    df = pressing_rankings(league_name, season)
    if df.empty or "ppda" not in df.columns:
        return None

    df = df.sort_values("ppda", ascending=False)

    norm       = Normalize(vmin=df["ppda"].min(), vmax=df["ppda"].max())
    bar_colors = [plt.cm.RdYlGn_r(norm(v)) for v in df["ppda"]]

    fig, ax = plt.subplots(figsize=(10, len(df) * 0.55 + 2.8), facecolor=BG)
    _style_ax(ax)

    bars = ax.barh(df["team"], df["ppda"], color=bar_colors, edgecolor="none", height=0.7)
    for bar, val in zip(bars, df["ppda"]):
        ax.text(val + 0.15, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}", va="center", ha="left", color=TEXT_SEC, fontsize=8.5)

    # Club identity badge near the start of each bar
    for bar, team in zip(bars, df["team"]):
        code        = PL_CLUB_CODES.get(team, team[:3].upper())
        club_color  = PL_CLUB_COLORS.get(team, ACCENT)
        text_color  = _text_color_for_bg(club_color)
        ax.text(df["ppda"].max() * 0.03, bar.get_y() + bar.get_height() / 2, code,
                va="center", ha="center", color=text_color, fontsize=7.8, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.28", facecolor=club_color, edgecolor="none"))

    # Callout on the standout team
    most_intense = df.iloc[-1]
    most_passive = df.iloc[0]
    ax.text(most_intense["ppda"] * 0.62, len(df) - 1, "MOST RELENTLESS",
            ha="center", va="center", color=BG, fontsize=7.5, fontweight="bold")

    ax.set_xlim(0, df["ppda"].max() * 1.1)
    ax.set_xlabel("PPDA — lower = chases the ball down faster", fontsize=10)
    ax.tick_params(axis="y", labelcolor=TEXT_PRI, labelsize=9.5)
    ax.grid(axis="x", color=GRID, lw=0.5, zorder=1)
    ax.set_axisbelow(True)

    fig.suptitle("Who Presses the Hardest?", color=TEXT_PRI, fontsize=16,
                fontweight="bold", y=0.985)
    fig.text(0.5, 0.955,
            f"{most_intense['team']} hunts the ball harder than anyone — "
            f"{most_passive['team']} is happy to sit back",
            ha="center", color=ACCENT, fontsize=10.5, style="italic")
    fig.text(0.5, 0.935,
            f"{league_name} {season}  ·  green = intense press, red = passive  ·  badge = club",
            ha="center", color=TEXT_SEC, fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.92])
    if save:
        _save(fig, league_name, f"pressing_{season}.png")
    return fig


def form_chart(team, league_name, season=CURRENT_SEASON, last_n=15, save=True):
    """
    Two-panel chart: cumulative points (top) and cumulative xG diff (bottom).
    Result badges coloured green/amber/red on x-axis labels.
    """
    df = team_form(league_name, season, team=team, last_n=last_n)
    if df.empty:
        return None

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), facecolor=BG,
                                    sharex=True,
                                    gridspec_kw={"height_ratios": [2, 1]})
    for ax in [ax1, ax2]:
        _style_ax(ax)

    x = range(1, len(df) + 1)

    ax1.plot(x, df["cumulative_points"], color=ACCENT, lw=2.5,
             marker="o", markersize=5, zorder=3)
    ax1.fill_between(x, df["cumulative_points"], alpha=0.15, color=ACCENT, zorder=2)
    ax1.set_ylabel("Cumulative Points", fontsize=10)
    ax1.grid(color=GRID, lw=0.5, zorder=1)

    if "cumulative_xg_diff" in df.columns:
        xg_vals = df["cumulative_xg_diff"]
        cols    = [ACCENT if v >= 0 else RED for v in xg_vals]
        ax2.bar(x, xg_vals, color=cols, alpha=0.75, edgecolor="none", width=0.6)
        ax2.axhline(0, color=TEXT_SEC, lw=0.8)
        ax2.set_ylabel("Cumul. xG Diff", fontsize=9)
        ax2.grid(color=GRID, lw=0.5, zorder=1)

    result_colors = {"W": ACCENT, "D": AMBER, "L": RED}
    labels = []
    for _, row in df.iterrows():
        res = row.get("result", "?")
        opp = row.get("opponent", "")
        ha  = row.get("home_away", "")
        labels.append(f"{ha} {opp[:10]}\n{res}")

    ax2.set_xticks(list(x))
    ax2.set_xticklabels(labels, fontsize=7.5)
    for tick, (_, row) in zip(ax2.get_xticklabels(), df.iterrows()):
        tick.set_color(result_colors.get(row.get("result", "?"), TEXT_SEC))

    ax1.set_title(
        f"{team} — Form & xG Trend (Last {last_n} Matches)\n{league_name} · {season}",
        color=TEXT_PRI, fontsize=13, fontweight="bold",
    )
    plt.tight_layout()

    if save:
        safe = team.replace(" ", "_").lower()
        _save(fig, league_name, f"form_{safe}_{season}.png")
    return fig


def xg_league_table_chart(league_name, season=CURRENT_SEASON, save=True):
    """
    Actual points vs expected points (derived from xG diff).
    Teams above the diagonal are outperforming their xG; below = underachieving.
    """
    df = league_table(league_name, season)
    if df.empty or "xg_diff" not in df.columns:
        return None

    df["expected_pts_approx"] = (df["points"].mean() + df["xg_diff"] * 1.5).clip(0)

    fig, ax = plt.subplots(figsize=(11, 9), facecolor=BG)
    _style_ax(ax)

    ax.scatter(df["expected_pts_approx"], df["points"],
               color=ACCENT, s=80, edgecolors=BG, linewidths=0.5, zorder=3, alpha=0.85)

    max_pts = max(df["points"].max(), df["expected_pts_approx"].max()) * 1.05
    ax.plot([0, max_pts], [0, max_pts], color=TEXT_SEC, lw=1, linestyle="--", alpha=0.5)
    ax.text(max_pts * 0.55, max_pts * 0.52, "Actual = Expected",
            color=TEXT_SEC, fontsize=8, alpha=0.6, rotation=43)

    for _, row in df.iterrows():
        short = row["team"].replace("Manchester", "Man")
        ax.annotate(short,
                    (row["expected_pts_approx"], row["points"]),
                    fontsize=7.5, color=TEXT_PRI, alpha=0.9,
                    xytext=(5, 3), textcoords="offset points")

    ax.set_xlabel("Expected Points (from xG Difference)", fontsize=11)
    ax.set_ylabel("Actual Points", fontsize=11)
    ax.set_title(f"Actual vs Expected Points\n{league_name} · {season}",
                 color=TEXT_PRI, fontsize=13, fontweight="bold")
    ax.grid(color=GRID, lw=0.5, zorder=1)
    plt.tight_layout()

    if save:
        _save(fig, league_name, f"xg_table_{season}.png")
    return fig
