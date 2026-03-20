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

The first command analyzes `market_archive/snapshots.jsonl`. The second appends one
public live-price snapshot to the same archive. Neither command uses wallet keys or
places trades.

Run the automated offline checks with:

```bash
python -m unittest discover -s tests
```

Recovered source files are retained under `antilego/recovered_collector/` and
`antilego/experimental_tracking/` for provenance. The active package entry points
are the Python modules directly inside `antilego/`.
