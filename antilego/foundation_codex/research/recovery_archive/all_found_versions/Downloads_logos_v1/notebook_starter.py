"""
LOGOS V1 — Analysis Notebook Starter
======================================
Copy these code blocks into Jupyter notebook cells.
Each # %% marks a new cell.

Run this AFTER you've collected some snapshots with snapshot_collector.py
"""

# %% [markdown]
# # LOGOS V1: Logical Optimization for Global Outcome Systems
# **Detecting logical inconsistencies in Polymarket prediction markets**
#
# Authors: Caleb Mukasa & [Partner Name]
# Date: March 2026

# %% — Cell 1: Imports
import json
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime

# %% — Cell 2: Load snapshot data
snapshots = [json.loads(line) for line in open("snapshots.jsonl")]
print(f"Loaded {len(snapshots)} snapshots")
print(f"Time range: {snapshots[0]['timestamp']} → {snapshots[-1]['timestamp']}")

# %% — Cell 3: Convert to flat DataFrame for analysis
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
                "coherent": family.get("coherent"),
                "violations": family.get("violations", 0),
                "sum": family.get("sum"),  # for mutually_exclusive only
            })

df = pd.DataFrame(rows)
df["timestamp"] = pd.to_datetime(df["timestamp"])
print(f"DataFrame: {len(df)} rows, {df['family'].nunique()} families")
df.head(10)

# %% — Cell 4: Price time series for each family
fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle("LOGOS V1 — Market Family Prices Over Time", fontsize=14)

for ax, family_name in zip(axes.flatten(), df["family"].unique()[:4]):
    fam = df[df["family"] == family_name]
    for label in fam["label"].unique():
        series = fam[fam["label"] == label]
        ax.plot(series["timestamp"], series["price"], label=label, linewidth=1)
    ax.set_title(family_name, fontsize=11)
    ax.set_ylabel("Probability")
    ax.legend(fontsize=7, loc="best")
    ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig("price_timeseries.png", dpi=150)
plt.show()

# %% — Cell 5: Violation frequency per snapshot
# Build a summary per snapshot per family
snap_summary = []
for snap in snapshots:
    ts = snap["timestamp"]
    for family in snap["families"]:
        snap_summary.append({
            "timestamp": ts,
            "family": family["name"],
            "family_type": family["type"],
            "coherent": family.get("coherent", True),
            "violations": family.get("violations", 0),
            "sum": family.get("sum"),
        })

sdf = pd.DataFrame(snap_summary)
sdf["timestamp"] = pd.to_datetime(sdf["timestamp"])

# Fraction of snapshots with violations, by family
violation_rate = sdf.groupby("family")["coherent"].apply(lambda x: 1 - x.mean())
print("Violation rate per family:")
print(violation_rate.round(4))

# %% [markdown]
# ## Next Steps
# After collecting enough data (24-48 hours), you can:
# 1. Run the constraint checker (Phase 3)
# 2. Run the cvxpy optimizer (Phase 4)
# 3. Compute frequency, magnitude, and persistence metrics (Phase 5)
#
# **Prompt for Claude to build the optimizer:**
# > "Using cvxpy, write a function called `project_to_coherent(observed_probs, family_type, exhaustive=True)` that takes a numpy array of observed market probabilities and a family type string, defines a cvxpy variable, minimizes sum of squared differences, and adds the appropriate constraints. Test with observed = [0.48, 0.52, 0.22] for a threshold_chain."
