<p align="center">
  <img src="assets/antilego_logo_wide.png" alt="Antilego logo" width="905">
</p>

# Antilego

Antilego is a read-only probability-consistency engine for prediction markets. It
collects public Polymarket prices, groups logically related contracts, and flags
deadline, threshold, and mutually exclusive probability violations.

## Run the current pipeline

```bash
python -m antilego.antilego_engine analyze
python -m antilego.antilego_engine collect
```

The first command analyzes the current weekly Antilego snapshot archive. The
second stores public live-price snapshots under the current week's Monday date,
for example `archive/2026-08-03/market_data/snapshots.jsonl`. Generated figures
and reports use sibling `figures/` and `reports/` folders. Neither command uses
wallet keys or places trades.

Run the automated offline checks with:

```bash
python -m unittest discover -s tests
```

The active package entry points are the Python modules directly inside `antilego/`.
Preserved foundational research is isolated from the runtime in
`antilego/foundation_codex/`.
