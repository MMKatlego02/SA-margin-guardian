"""Visuals for the video: BMW, VW and Kia. Reads margin_results.csv (made by margin_guardian.py) and
writes four 1920x1080 PNGs into ./visuals. Re-run any time your data or assumptions change:

    py -m pip install matplotlib pandas numpy
    py Brands_visuals.py

Titles are built from the data, so they stay true when the numbers change.
"""
from pathlib import Path
import sys

import matplotlib
from matplotlib.patches import Patch

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    import config
    THRESHOLD = float(config.THRESHOLD_PCT)
except Exception:
    THRESHOLD = 4.0
    print("Note: could not read THRESHOLD_PCT from config.py, using 4.0%")

HERE = Path(__file__).parent
OUT = HERE / "visuals"
BRANDS = ["BMW", "VW", "Kia"]
COLORS = {"BMW": "#1C69D4", "VW": "#2A9D8F", "Kia": "#D6264A"}
ACTIONS = ["HOLD", "PRICE INTERVENTION", "SEND TO AUCTION"]
ACTION_COLORS = {"HOLD": "#8FA3B3", "PRICE INTERVENTION": "#F2A541", "SEND TO AUCTION": "#C8102E"}
INK, MUTED, GRID = "#111827", "#4B5563", "#E5E7EB"
TITLE_SIZE = 24

REQUIRED_COLUMNS = ["vehicle_id", "brand", "days_on_lot", "projected_profit", "projected_sale_price",
                    "flagged", "at_risk_rand", "recommendation", "margin_pct"]

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Inter", "Segoe UI", "Arial", "Helvetica", "DejaVu Sans"]


def rand(n: float) -> str:
    return "R" + f"{n:,.0f}".replace(",", " ")           # South African style: R91 365


def load():
    path = HERE / "margin_results.csv"
    if not path.exists():
        sys.exit(f"Cannot find {path}. Run margin_guardian.py first.")

    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"margin_results.csv is missing columns: {', '.join(missing)}")

    df["brand"] = df["brand"].astype(str).str.strip()
    df["recommendation"] = df["recommendation"].astype(str).str.strip()

    sub = df[df["brand"].isin(BRANDS)]
    if sub.empty:
        sys.exit(f"No rows found for brands {BRANDS}. Check the brand names in margin_results.csv.")

    g = sub.groupby("brand").agg(n=("vehicle_id", "count"), avg_days=("days_on_lot", "mean"),
                                 profit=("projected_profit", "sum"), price=("projected_sale_price", "sum"),
                                 flagged=("flagged", "sum"), at_risk=("at_risk_rand", "sum")).reindex(BRANDS)
    g = g.fillna(0)                                       # a brand with no rows shows as zeros, not a crash
    g["wm"] = (100 * g["profit"] / g["price"]).where(g["price"] > 0, 0.0)
    g["pct_flag"] = (100 * g["flagged"] / g["n"]).where(g["n"] > 0, 0.0)
    return df, sub, g


def base_fig(title, subtitle, total):
    fig = plt.figure(figsize=(12.8, 7.2), dpi=150, facecolor="white")
    fig.text(0.06, 0.94, title, fontsize=TITLE_SIZE, fontweight="bold", color=INK, va="top")
    fig.text(0.06, 0.865, subtitle, fontsize=15, color=MUTED, va="top")
    fig.text(0.06, 0.03, f"Synthetic data from SA_Margin_Guardian ({total} vehicles in total). Small samples per brand; "
             "differences are not tested for significance.", fontsize=11.5, color="#6B7280", va="bottom")
    return fig


def clean_axes(ax):
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color("#9CA3AF")
    ax.tick_params(axis="both", length=0, labelsize=14, colors=MUTED)


def visual_margin(g, total):
    top = g["wm"].idxmax()
    fig = base_fig(f"{top} has the highest weighted margin of the three brands",
                   f"Projected gross margin, weighted by sale price. Dashed line = {THRESHOLD:g}% flag threshold.", total)
    ax = fig.add_axes((0.08, 0.13, 0.86, 0.66))
    x = np.arange(len(BRANDS))
    ax.bar(x, g["wm"], width=0.55, color=[COLORS[b] for b in BRANDS], zorder=3)
    ax.axhline(THRESHOLD, ls="--", lw=2, color="#374151", zorder=4)
    ax.text(len(BRANDS) - 0.4, THRESHOLD + 0.15, f"{THRESHOLD:g}% flag threshold", ha="left", va="bottom",
            fontsize=14, color="#374151")
    for i, b in enumerate(BRANDS):
        ax.text(i, g.loc[b, "wm"] + 0.2, f"{g.loc[b, 'wm']:.1f}%", ha="center", va="bottom", fontsize=24,
                fontweight="bold", color=COLORS[b])
        ax.text(i, 0.35, f"n = {int(g.loc[b, 'n'])} vehicles", ha="center", va="bottom", fontsize=14,
                color="white", zorder=5)
    ax.set_xticks(x, BRANDS, fontsize=21, fontweight="bold")
    ax.set_xlim(-0.6, len(BRANDS) + 0.45)
    ax.set_ylim(0, max(g["wm"].max() * 1.22, THRESHOLD * 1.5))
    ax.set_ylabel("Weighted margin (%)", fontsize=14, color=MUTED)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    clean_axes(ax)
    return fig


def visual_mix(sub, g, total):
    top = g["pct_flag"].idxmax()
    fig = base_fig(f"{top} has the largest share of vehicles flagged for action",
                   "Share of each brand's vehicles by recommended action", total)
    ax = fig.add_axes((0.10, 0.14, 0.70, 0.58))
    mix = (sub.groupby(["brand", "recommendation"]).size().unstack(fill_value=0)
           .reindex(index=BRANDS, columns=ACTIONS, fill_value=0))
    ypos = np.arange(len(BRANDS))[::-1]
    for i, b in enumerate(BRANDS):
        left, brand_n = 0.0, mix.loc[b].sum()
        if brand_n == 0:
            continue
        for a in ACTIONS:
            w = 100 * mix.loc[b, a] / brand_n
            ax.barh(ypos[i], w, left=left, height=0.55, color=ACTION_COLORS[a], zorder=3)
            if w >= 3:
                ax.text(left + w / 2, ypos[i], str(int(mix.loc[b, a])), ha="center", va="center", fontsize=16,
                        fontweight="bold", color="white" if a != "PRICE INTERVENTION" else INK, zorder=4)
            left += w
        flagged = int(g.loc[b, "flagged"])
        ax.text(101.5, ypos[i], f"{flagged} of {int(g.loc[b, 'n'])} flagged ({g.loc[b, 'pct_flag']:.0f}%)",
                va="center", ha="left", fontsize=15, color=INK, clip_on=False)
    ax.set_yticks(ypos, BRANDS, fontsize=21, fontweight="bold")
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%"])
    ax.xaxis.grid(True, color=GRID, zorder=0)
    clean_axes(ax)
    handles = [Patch(color=ACTION_COLORS[a]) for a in ACTIONS]
    names = {"HOLD": "Hold", "PRICE INTERVENTION": "Price intervention", "SEND TO AUCTION": "Send to auction"}
    ax.legend(handles, [names[a] for a in ACTIONS], loc="lower left", bbox_to_anchor=(0, 1.04), ncol=3,
              frameon=False, fontsize=15)
    return fig


def visual_scatter(sub, total):
    fig = base_fig("Projected margin falls as vehicles sit longer",
                   "By design, holding cost and depreciation grow daily. Each dot is a vehicle; below the dashed line = flagged.",
                   total)
    ax = fig.add_axes((0.08, 0.17, 0.86, 0.62))
    for b in BRANDS:
        d = sub[sub["brand"] == b]
        ax.scatter(d["days_on_lot"], d["margin_pct"], s=110, color=COLORS[b], alpha=0.85, edgecolor="white",
                   linewidth=1.2, label=f"{b} (n = {len(d)})", zorder=3)
    ax.axhline(THRESHOLD, ls="--", lw=2, color="#374151", zorder=4)
    lo = min(sub["margin_pct"].min() - 2, -2)
    ax.axhspan(lo, THRESHOLD, color="#FDE8EC", alpha=0.6, zorder=1)
    ax.set_ylim(lo, sub["margin_pct"].max() + 2)
    ax.text(sub["days_on_lot"].max() * 0.995, THRESHOLD + 0.5, f"{THRESHOLD:g}% flag threshold", ha="right",
            va="bottom", fontsize=14, color="#374151")
    ax.set_xlabel("Days on lot", fontsize=15, color=MUTED)
    ax.set_ylabel("Projected margin (%)", fontsize=15, color=MUTED)
    ax.yaxis.grid(True, color=GRID, zorder=0)
    ax.legend(loc="upper right", frameon=False, fontsize=16, markerscale=1.3)
    clean_axes(ax)
    return fig


def visual_scorecard(g, total):
    fig = base_fig("BMW, VW and Kia at a glance",
                   f"Base case of SA_Margin_Guardian, {THRESHOLD:g}% flag threshold", total)
    ax = fig.add_axes((0.06, 0.14, 0.88, 0.64))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    cols = [("Brand", 8, "left"), ("Vehicles", 30, "right"), ("Avg days on lot", 47, "right"),
            ("Weighted margin", 66, "right"), ("Flagged", 82, "right"), ("Rand at risk", 99, "right")]
    for name, x, ha in cols:
        ax.text(x, 90, name, ha=ha, va="center", fontsize=16, fontweight="bold", color=MUTED)
    ax.plot([0, 100], [82, 82], color="#9CA3AF", lw=2)
    for i, b in enumerate(BRANDS):
        y = 66 - i * 25
        ax.scatter([4.0], [y], s=420, color=COLORS[b], clip_on=False, zorder=3)
        ax.text(8, y, b, ha="left", va="center", fontsize=26, fontweight="bold", color=INK)
        vals = [str(int(g.loc[b, "n"])), f"{g.loc[b, 'avg_days']:.0f}", f"{g.loc[b, 'wm']:.1f}%",
                f"{int(g.loc[b, 'flagged'])} ({g.loc[b, 'pct_flag']:.0f}%)", rand(g.loc[b, "at_risk"])]
        for (name, x, ha), v in zip(cols[1:], vals):
            ax.text(x, y, v, ha=ha, va="center", fontsize=24, color=INK)
        ax.plot([0, 100], [y - 12.5, y - 12.5], color=GRID, lw=1.5)
    return fig


def main():
    OUT.mkdir(exist_ok=True)
    df, sub, g = load()
    total = len(df)
    figs = {
        "1_weighted_margin_by_brand.png": visual_margin(g, total),
        "2_recommended_action_by_brand.png": visual_mix(sub, g, total),
        "3_margin_vs_days_on_lot.png": visual_scatter(sub, total),
        "4_brand_scorecard.png": visual_scorecard(g, total),
    }
    for name, fig in figs.items():
        fig.savefig(OUT / name, facecolor="white")
        plt.close(fig)
        print("saved", OUT / name)


if __name__ == "__main__":
    main()
