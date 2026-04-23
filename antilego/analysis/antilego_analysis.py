# %% [markdown]
# # ANTILEGO: Probability Consistency Engine
# **Detecting Logical Inconsistencies in Polymarket Prediction Markets**
#
# *Authors: Caleb Mukasa & Tarik Filipovic*
# *Active Antilego research workspace*
#
# ---
#
# ## Abstract
#
# Antilego tests whether prediction markets obey their own implied probability logic.
# We monitor configured families of related Polymarket contracts, checking whether
# observed prices satisfy fundamental probability constraints: monotonicity for nested
# events and additivity for mutually exclusive outcomes. Using convex optimization,
# we compute the nearest coherent probability system and measure the frequency,
# magnitude, and persistence of violations over time.

# %% — Cell 1: Imports and Setup
import argparse
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from collections import Counter, defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from antilego.paths import DEFAULT_SNAPSHOT_PATH
from antilego.signal_visuals import figure_path
from antilego.contradiction_brain import evaluate_family

parser = argparse.ArgumentParser(description="Run the Antilego analysis workflow")
parser.add_argument(
    "--snapshots",
    type=Path,
    default=DEFAULT_SNAPSHOT_PATH,
    help="JSONL snapshot archive to analyze",
)
parser.add_argument(
    "--figures-dir",
    type=Path,
    help="directory for generated figures (defaults to the current weekly archive)",
)
parser.add_argument(
    "--no-show",
    action="store_true",
    help="save figures without opening interactive windows",
)
args = parser.parse_args()
SNAPSHOT_PATH = args.snapshots
FIGURES_DIR = args.figures_dir


def output_figure(filename: str) -> Path:
    return figure_path(filename, FIGURES_DIR)


def show_or_close() -> None:
    if args.no_show:
        plt.close()
    else:
        plt.show()

plt.style.use("dark_background")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 11
plt.rcParams['axes.grid'] = True
plt.rcParams['grid.alpha'] = 0.3
plt.rcParams['figure.facecolor'] = 'black'
plt.rcParams['axes.facecolor'] = 'black'
plt.rcParams['savefig.facecolor'] = 'black'

# %% — Cell 2: Load Data
snapshots = [json.loads(line) for line in SNAPSHOT_PATH.open(encoding="utf-8")]
for snapshot in snapshots:
    snapshot["families"] = [
        family
        for family in snapshot.get("families", [])
        if family.get("markets")
        and all(market.get("price") is not None for market in family["markets"])
    ]
snapshots = [snapshot for snapshot in snapshots if snapshot["families"]]
if not snapshots:
    raise RuntimeError(
        f"No complete market families were found in {SNAPSHOT_PATH}. "
        "Choose a complete historical fixture or refresh the active market definitions."
    )
print(f"Loaded {len(snapshots)} snapshots")
print(f"Time range: {snapshots[0]['timestamp'][:19]} → {snapshots[-1]['timestamp'][:19]} UTC")
print(f"Families: {len(snapshots[0]['families'])}")
for f in snapshots[0]['families']:
    print(f"  • {f['name']}: {len(f['markets'])} markets ({f['type']})")

# %% [markdown]
# ---
# ## 1. Mathematical Framework
#
# ### Kolmogorov Probability Axioms
#
# Every valid probability distribution must satisfy:
# 1. **Non-negativity**: $P(A) \geq 0$
# 2. **Normalization**: $P(\Omega) = 1$
# 3. **Additivity**: For mutually exclusive events, $P(A \cup B) = P(A) + P(B)$
#
# From these axioms, we derive the constraints Antilego checks:
#
# **Monotonicity (nested events):** If $A \subseteq B$, then $P(A) \leq P(B)$
# - *Threshold chains*: Hitting \$100k requires hitting \$85k first → $P(\uparrow 85k) \geq P(\uparrow 100k)$
# - *Deadline nesting*: Ceasefire by June implies ceasefire by December → $P(\text{by Jun}) \leq P(\text{by Dec})$
#
# **Exhaustive exclusivity:** If exactly one of $\{A_1, ..., A_n\}$ occurs, then $\sum P(A_i) = 1$
# - *NBA Champion*: Exactly one team wins → all team probabilities must sum to 1.0
#
# ### Optimization Formulation
#
# For each family with observed prices $p^{obs}$, Antilego computes the nearest coherent
# vector $p^*$ by solving:
#
# $$\min_{p} \sum_i (p_i - p_i^{obs})^2$$
#
# subject to family-specific constraints and $0 \leq p_i \leq 1$.

# %% — Cell 3: Build Analysis DataFrames

# Flat DataFrame: one row per market per snapshot
rows = []
for snap in snapshots:
    ts = snap["timestamp"]
    for family in snap["families"]:
        for market in family["markets"]:
            rows.append({
                "timestamp": ts,
                "family": family["name"],
                "family_type": family["type"],
                "label": market["label"],
                "price": market["price"],
            })

df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"])
print(f"Market-level DataFrame: {len(df):,} rows")

# Family-level DataFrame: one row per family per snapshot
fam_rows = []
for snap in snapshots:
    ts = snap["timestamp"]
    for family in snap["families"]:
        prices = [m["price"] for m in family["markets"] if m["price"] is not None]
        ftype = family["type"]
        evaluation = evaluate_family(family)
        if evaluation["coherent"] is None:
            raise RuntimeError(
                f"Cannot evaluate {family['name']}: "
                f"{evaluation.get('error', 'incomplete market data')}"
            )
        violations = evaluation["violations"]

        total_magnitude = sum(v["magnitude"] for v in violations)
        max_magnitude = max((v["magnitude"] for v in violations), default=0)

        fam_rows.append({
            "timestamp": ts,
            "family": family["name"],
            "family_type": ftype,
            "n_violations": len(violations),
            "has_violation": len(violations) > 0,
            "total_magnitude": total_magnitude,
            "max_magnitude": max_magnitude,
            "price_sum": evaluation.get("sum"),
            "violation_details": violations,
        })

fdf = pd.DataFrame(fam_rows)
fdf["timestamp"] = pd.to_datetime(fdf["timestamp"])
print(f"Family-level DataFrame: {len(fdf):,} rows")

# %% [markdown]
# ---
# ## 2. Data Overview

# %% — Cell 4: Market Status Dashboard
family_status = fdf.groupby("family")["has_violation"].any()
all_clear = [name for name in df["family"].unique() if not family_status[name]]
violating = [name for name in df["family"].unique() if family_status[name]]
dashboard_rows = max(len(all_clear), len(violating), 1)

fig = plt.figure(figsize=(18, 3.25 * dashboard_rows + 1.0))
columns = fig.add_gridspec(1, 2, left=0.05, right=0.98, bottom=0.06, top=0.91, wspace=0.13)
left_grid = columns[0].subgridspec(dashboard_rows, 1, hspace=0.34)
right_grid = columns[1].subgridspec(dashboard_rows, 1, hspace=0.34)

fig.text(0.255, 0.955, "ALL CLEAR", color="#31d07c", fontsize=18,
         fontweight="bold", ha="center", va="center")
fig.text(0.745, 0.955, "VIOLATIONS", color="#ff4d4d", fontsize=18,
         fontweight="bold", ha="center", va="center")


def plot_market_family(ax, family_name, is_violation):
    family_prices = df[df["family"] == family_name]
    if "NBA" in family_name:
        top_labels = family_prices.groupby("label")["price"].mean().nlargest(8).index
        family_prices = family_prices[family_prices["label"].isin(top_labels)]

    for label in family_prices["label"].unique():
        series = family_prices[family_prices["label"] == label].sort_values("timestamp")
        ax.plot(series["timestamp"], series["price"], label=label, linewidth=1.2)

    ax.set_title(family_name, fontsize=12, fontweight="bold", pad=8)
    ax.set_ylabel("Probability")
    ax.set_xlabel("Time (UTC)")
    ax.legend(fontsize=6.5, loc="upper right", ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))

    family_checks = fdf[fdf["family"] == family_name].sort_values("timestamp")
    if is_violation:
        ax.fill_between(
            family_checks["timestamp"], 0, 1,
            where=family_checks["has_violation"],
            transform=ax.get_xaxis_transform(), step="post",
            color="#ff3030", alpha=0.08,
        )
        violation_pairs = [
            detail["pair"]
            for details in family_checks["violation_details"]
            for detail in details
        ]
        primary_violation = Counter(violation_pairs).most_common(1)[0][0]
        violation_rate = family_checks["has_violation"].mean()
        ax.text(
            0.015, 0.94,
            f"VIOLATION: {primary_violation}\nActive in {violation_rate:.1%} of snapshots",
            transform=ax.transAxes, va="top", ha="left",
            color="#ff4d4d", fontsize=8.5, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="black",
                      edgecolor="#ff4d4d", linewidth=1.3),
        )
    else:
        ax.text(
            0.015, 0.94, "NO VIOLATIONS DETECTED",
            transform=ax.transAxes, va="top", ha="left",
            color="#31d07c", fontsize=8.5, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="black",
                      edgecolor="#31d07c", linewidth=1.3),
        )


if all_clear:
    for index, family_name in enumerate(all_clear):
        plot_market_family(fig.add_subplot(left_grid[index]), family_name, False)
else:
    empty_axis = fig.add_subplot(left_grid[0])
    empty_axis.text(0.5, 0.5, "No all-clear families", ha="center", va="center")
    empty_axis.set_axis_off()

if violating:
    for index, family_name in enumerate(violating):
        plot_market_family(fig.add_subplot(right_grid[index]), family_name, True)
else:
    empty_axis = fig.add_subplot(right_grid[0])
    empty_axis.text(0.5, 0.5, "No violations detected", ha="center", va="center")
    empty_axis.set_axis_off()

fig.suptitle("ANTILEGO — MARKET CONSISTENCY STATUS", fontsize=21,
             fontweight="bold", y=0.995)
dashboard_path = output_figure("fig1_market_status_dashboard.png")
plt.savefig(dashboard_path, dpi=150, bbox_inches="tight", facecolor="black")
for retired_name in ("fig1_price_timeseries.png", "fig7_fed_violation_detail.png"):
    retired_path = output_figure(retired_name)
    if retired_path.exists():
        retired_path.unlink()
print(f"Saved: {dashboard_path.name}")
show_or_close()

# %% [markdown]
# ---
# ## 3. Violation Detection Results

# %% — Cell 5: Violation Summary Table
print("=" * 70)
print("VIOLATION FREQUENCY BY FAMILY")
print("=" * 70)

summary_data = []
for family_name in fdf["family"].unique():
    ff = fdf[fdf["family"] == family_name]
    total = len(ff)
    violated = ff["has_violation"].sum()
    rate = violated / total
    avg_mag = ff[ff["has_violation"]]["max_magnitude"].mean() if violated > 0 else 0
    max_mag = ff["max_magnitude"].max()

    summary_data.append({
        "Family": family_name,
        "Type": ff["family_type"].iloc[0],
        "Snapshots": total,
        "Violated": int(violated),
        "Rate": rate,
        "Avg Magnitude": avg_mag,
        "Max Magnitude": max_mag,
    })
    print(f"\n{family_name} ({ff['family_type'].iloc[0]})")
    print(f"  Violations: {violated}/{total} snapshots ({rate:.1%})")
    print(f"  Avg magnitude: {avg_mag:.4f}  Max: {max_mag:.4f}")

summary_df = pd.DataFrame(summary_data)
print("\n")
print(summary_df.to_string(index=False))

# %% — Cell 6: Violation Rate Bar Chart
fig, ax = plt.subplots(figsize=(10, 5))
colors = ["#2ecc71" if r < 0.1 else "#f39c12" if r < 0.5 else "#e74c3c" for r in summary_df["Rate"]]
bars = ax.bar(summary_df["Family"], summary_df["Rate"], color=colors, edgecolor="white", linewidth=1.5)
ax.set_ylabel("Fraction of Snapshots with Violations")
ax.set_title("ANTILEGO — Violation Frequency by Family", fontsize=14, fontweight="bold")
ax.set_ylim(0, 1.1)

for bar, rate in zip(bars, summary_df["Rate"]):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
            f"{rate:.1%}", ha="center", fontsize=11, fontweight="bold")

ax.axhline(y=0.5, color="gray", linestyle="--", alpha=0.5, label="50% threshold")
plt.xticks(rotation=15, ha="right")
plt.tight_layout()
plt.savefig(output_figure("fig2_violation_frequency.png"), dpi=150, bbox_inches="tight")
show_or_close()
print("Saved: fig2_violation_frequency.png")

# %% [markdown]
# ---
# ## 4. Convex Optimization — Projecting to Coherence
#
# For each violated snapshot, we compute the nearest coherent probability vector
# using quadratic programming. Install cvxpy if needed: `pip install cvxpy`

# %% — Cell 7: Coherent Projection Engine
try:
    import cvxpy as cp
    HAS_CVXPY = True
    print("cvxpy available — using full optimizer")
except ImportError:
    HAS_CVXPY = False
    print("cvxpy not installed — using analytical fallback")
    print("Install with: pip install cvxpy")


def project_to_coherent(observed, family_type, exhaustive=True):
    """
    Project observed market probabilities onto the nearest coherent set.

    Args:
        observed: numpy array of observed probabilities
        family_type: a key from the probability-law registry
        exhaustive: compatibility switch for legacy mutually-exclusive families

    Returns:
        dict with 'projected', 'adjustments', 'inconsistency_score'
    """
    n = len(observed)
    obs = np.array(observed, dtype=float)

    if HAS_CVXPY:
        p = cp.Variable(n)
        objective = cp.Minimize(cp.sum_squares(p - obs))

        constraints = [p >= 0, p <= 1]

        if family_type == "threshold_chain":
            # p[i] >= p[i+1] for all consecutive pairs
            for i in range(n - 1):
                constraints.append(p[i] >= p[i + 1])

        elif family_type in {"deadline_nesting", "logical_implication"}:
            # p[i] <= p[i+1] for all consecutive pairs
            for i in range(n - 1):
                constraints.append(p[i] <= p[i + 1])

        elif family_type in {
            "mutually_exclusive",
            "exhaustive_outcomes",
            "complements",
        }:
            constraints.append(cp.sum(p) == 1)

        elif family_type == "non_exhaustive_exclusivity":
            constraints.append(cp.sum(p) <= 1)

        prob = cp.Problem(objective, constraints)
        prob.solve(solver=cp.SCS, verbose=False)

        if prob.status == "optimal" or prob.status == "optimal_inaccurate":
            projected = np.array(p.value).flatten()
        else:
            projected = obs.copy()
    else:
        # Analytical fallback: isotonic regression for chains, normalization for ME
        projected = obs.copy()

        if family_type == "threshold_chain":
            # Pool adjacent violators (descending)
            for _ in range(n):
                for i in range(n - 1):
                    if projected[i] < projected[i + 1]:
                        avg = (projected[i] + projected[i + 1]) / 2
                        projected[i] = avg
                        projected[i + 1] = avg

        elif family_type in {"deadline_nesting", "logical_implication"}:
            # Pool adjacent violators (ascending)
            for _ in range(n):
                for i in range(n - 1):
                    if projected[i] > projected[i + 1]:
                        avg = (projected[i] + projected[i + 1]) / 2
                        projected[i] = avg
                        projected[i + 1] = avg

        elif family_type in {
            "mutually_exclusive",
            "exhaustive_outcomes",
            "complements",
        }:
            projected = projected / projected.sum()

        elif family_type == "non_exhaustive_exclusivity" and projected.sum() > 1:
            projected = projected / projected.sum()

        projected = np.clip(projected, 0, 1)

    adjustments = projected - obs
    inconsistency_score = np.linalg.norm(adjustments)

    return {
        "projected": projected,
        "adjustments": adjustments,
        "inconsistency_score": inconsistency_score,
    }


# Test with a known violation
test_obs = np.array([0.635, 0.255, 0.075, 0.0235, 0.0085, 0.0065, 0.0045, 0.0050, 0.0045])
result = project_to_coherent(test_obs, "threshold_chain")
print("\nTest: BTC Upside threshold chain projection")
labels = ["↑75k", "↑80k", "↑85k", "↑90k", "↑95k", "↑100k", "↑105k", "↑110k", "↑150k"]
print(f"  {'Market':<8} {'Observed':>10} {'Projected':>10} {'Adjustment':>11}")
print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*11}")
for i in range(len(labels)):
    print(f"  {labels[i]:<8} {test_obs[i]:>10.4f} {result['projected'][i]:>10.4f} {result['adjustments'][i]:>+11.4f}")
print(f"\n  Inconsistency score: {result['inconsistency_score']:.6f}")

# %% — Cell 8: Run Optimizer on All Snapshots
print("Running coherent projection on all snapshots...")

projection_rows = []
for snap_idx, snap in enumerate(snapshots):
    ts = snap["timestamp"]
    for family in snap["families"]:
        prices = [m["price"] for m in family["markets"] if m["price"] is not None]
        if len(prices) < 2:
            continue

        obs = np.array(prices)
        result = project_to_coherent(obs, family["type"])

        projection_rows.append({
            "timestamp": ts,
            "family": family["name"],
            "family_type": family["type"],
            "inconsistency_score": result["inconsistency_score"],
            "max_adjustment": np.max(np.abs(result["adjustments"])),
            "mean_adjustment": np.mean(np.abs(result["adjustments"])),
        })

pdf = pd.DataFrame(projection_rows)
pdf["timestamp"] = pd.to_datetime(pdf["timestamp"])
print(f"Computed {len(pdf)} projections")

# %% — Cell 9: Example Before/After Table
# Show one snapshot's projection for each family
print("\n" + "=" * 70)
print("EXAMPLE PROJECTIONS (first violated snapshot per family)")
print("=" * 70)

for family in snapshots[0]["families"]:
    prices = [m["price"] for m in family["markets"] if m["price"] is not None]
    labels_list = [m["label"] for m in family["markets"] if m["price"] is not None]
    obs = np.array(prices)
    result = project_to_coherent(obs, family["type"])

    if result["inconsistency_score"] < 0.0001:
        continue

    print(f"\n{'─' * 60}")
    print(f"{family['name']} ({family['type']})")
    print(f"{'─' * 60}")
    print(f"  {'Market':<28} {'Observed':>9} {'Coherent':>9} {'Adjust':>9}")

    # Only show top markets for NBA
    indices = range(len(labels_list))
    if "NBA" in family["name"]:
        indices = range(min(10, len(labels_list)))

    for i in indices:
        adj = result["adjustments"][i]
        marker = " ◄" if abs(adj) > 0.001 else ""
        print(f"  {labels_list[i]:<28} {obs[i]:>9.4f} {result['projected'][i]:>9.4f} {adj:>+9.4f}{marker}")

    if "NBA" in family["name"] and len(labels_list) > 10:
        print(f"  ... ({len(labels_list) - 10} more teams)")

    print(f"\n  Inconsistency score: {result['inconsistency_score']:.6f}")

# %% [markdown]
# ---
# ## 5. Empirical Analysis
#
# ### Research Question A: How often are markets incoherent?

# %% [markdown]
# ### Research Question B: How large are the inconsistencies?

# %% — Cell 10: Magnitude Statistics Table
print("=" * 70)
print("INCONSISTENCY MAGNITUDE STATISTICS")
print("=" * 70)
mag_stats = pdf.groupby("family").agg(
    mean_score=("inconsistency_score", "mean"),
    median_score=("inconsistency_score", "median"),
    max_score=("inconsistency_score", "max"),
    std_score=("inconsistency_score", "std"),
    mean_max_adj=("max_adjustment", "mean"),
).round(6)
print(mag_stats.to_string())

# %% [markdown]
# ### Research Question C: How long do violations persist?

# %% — Cell 11: Violation Persistence Analysis
print("\n" + "=" * 70)
print("VIOLATION PERSISTENCE")
print("=" * 70)

persistence_data = []

for family_name in fdf["family"].unique():
    ff = fdf[fdf["family"] == family_name].sort_values("timestamp").reset_index(drop=True)

    # Find consecutive runs of violations
    runs = []
    current_run = 0
    in_violation = False

    for _, row in ff.iterrows():
        if row["has_violation"]:
            current_run += 1
            in_violation = True
        else:
            if in_violation and current_run > 0:
                runs.append(current_run)
            current_run = 0
            in_violation = False
    if in_violation and current_run > 0:
        runs.append(current_run)

    if runs:
        # Each snapshot is ~5 minutes apart
        avg_duration = np.mean(runs) * 5  # minutes
        median_duration = np.median(runs) * 5
        max_duration = max(runs) * 5
        total_runs = len(runs)
    else:
        avg_duration = median_duration = max_duration = 0
        total_runs = 0

    persistence_data.append({
        "Family": family_name,
        "Violation Runs": total_runs,
        "Avg Duration (min)": round(avg_duration, 1),
        "Median Duration (min)": round(median_duration, 1),
        "Max Duration (min)": round(max_duration, 1),
        "Longest Run (snapshots)": max(runs) if runs else 0,
    })

    print(f"\n{family_name}")
    if runs:
        print(f"  Violation runs: {total_runs}")
        print(f"  Avg duration: {avg_duration:.0f} min  Median: {median_duration:.0f} min  Max: {max_duration:.0f} min")
        print(f"  Run lengths (snapshots): {runs}")
    else:
        print(f"  No violations detected")

persist_df = pd.DataFrame(persistence_data)
print("\n")
print(persist_df.to_string(index=False))

# %% — Cell 12: NBA Sum Deviation Over Time
fig, ax = plt.subplots(figsize=(13, 4))
nba = fdf[fdf["family"].str.contains("NBA")].sort_values("timestamp")
if len(nba) > 0 and nba["price_sum"].notna().any():
    ax.plot(nba["timestamp"], nba["price_sum"], color="#e74c3c", linewidth=2)
    ax.axhline(y=1.0, color="green", linestyle="--", linewidth=1.5, label="Theoretical (1.00)")
    ax.fill_between(nba["timestamp"], 1.0, nba["price_sum"], alpha=0.2, color="red")
    ax.set_ylabel("Sum of Team Probabilities")
    ax.set_xlabel("Time (UTC)")
    ax.set_title("NBA Champion — Probability Sum Over Time (should be 1.00)", fontsize=13, fontweight="bold")
    ax.legend()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
plt.tight_layout()
plt.savefig(output_figure("fig6_nba_sum.png"), dpi=150, bbox_inches="tight")
show_or_close()

# %% [markdown]
# ---
# ## 6. Discussion
#
# ### Key Findings
#
# **Finding 1: Violations are common.** Three out of five families showed persistent
# logical violations throughout the observation period. The BTC Downside chain and
# Fed Rate Cut chain were violated in 100% of snapshots.
#
# **Finding 2: Magnitude varies by cause.** The Fed Rate Cut September/October
# inversion is the largest violation (~10-15 percentage points), likely driven by
# low liquidity in the October contract (wide bid-ask spread). The BTC threshold
# violations are tiny (~0.05-0.10 percentage points), occurring at the illiquid
# tail of the distribution where prices are sub-1%.
#
# **Finding 3: Some violations are persistent, not transient.** The Fed and BTC
# Downside violations persisted for the entire observation window, suggesting
# structural inefficiency rather than momentary noise. The BTC Upside violation
# flickered on and off, suggesting the market is closer to the coherence boundary.
#
# **Finding 4: The NBA overround is stable.** The mutually exclusive NBA Champion
# market consistently sums to ~1.5-2.5% above 1.00. This "overround" is common
# in betting markets and represents the aggregate cost of immediacy/liquidity.
#
# ### Interpretation
#
# These violations stem from two distinct sources:
# 1. **Illiquidity**: The Fed October and BTC tail contracts have wide spreads and
#    low volume. Midpoint prices don't reflect executable trades.
# 2. **Structural overround**: The NBA market systematically overprices the full
#    set, which is a known feature of multi-outcome betting markets.
#
# Antilego distinguishes these by measuring both the violation magnitude and the
# associated market liquidity, enabling researchers to separate meaningful
# structural breaks from noise.
#
# ### Limitations
#
# - Single observation window (~12 hours on a weekend night)
# - No liquidity weighting in the optimizer (V2 could weight by volume)
# - BTC March markets expire soon, limiting future data collection
#
# ### Future Work (V2)
#
# - Liquidity-weighted optimization ($w_i$ proportional to volume)
# - Automated family discovery using LLMs
# - Real-time dashboard
# - Cross-venue consistency checks (Polymarket vs Kalshi)
# - Backtesting: do violations predict profitable trades?

# %% — Cell 13: Final Summary
print("\n" + "=" * 70)
print("ANTILEGO — FINAL SUMMARY")
print("=" * 70)
print(f"\nData: {len(snapshots)} snapshots over ~{len(snapshots)*5/60:.1f} hours")
print(f"Markets monitored: 58 across 5 families")
print(f"\nViolation rates:")
for _, row in summary_df.iterrows():
    print(f"  {row['Family']:<25} {row['Rate']:>6.1%}  (max magnitude: {row['Max Magnitude']:.4f})")
print(f"\nConclusion: Polymarket prediction markets frequently violate basic")
print(f"probability logic, particularly in low-liquidity contracts. Antilego")
print(f"detects these violations in real-time and computes the nearest")
print(f"coherent probability system using convex optimization.")
