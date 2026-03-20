# LOGOS V1 — Starter Kit

## Quick Start

### 1. Install dependencies
```bash
pip install requests
```

### 2. Take a single test snapshot
```bash
python snapshot_collector.py
```
This will print all current prices and save one snapshot to `snapshots.jsonl`.

### 3. Start collecting data (run overnight!)
```bash
python snapshot_collector.py --loop 5
```
This takes a snapshot every 5 minutes until you hit Ctrl+C.
Leave it running overnight or over a weekend to build up data.

### 4. Analyze in Jupyter
Open `notebook_starter.py` and copy the cells into a Jupyter notebook.
Or convert it directly:
```bash
pip install jupytext
jupytext --to notebook notebook_starter.py
```

## Files

| File | What it does |
|---|---|
| `families.py` | All 4 market family definitions with asset IDs |
| `snapshot_collector.py` | Polls Polymarket API, saves timestamped snapshots |
| `notebook_starter.py` | Starter code for Jupyter analysis |
| `snapshots.jsonl` | Your collected data (created when you run the collector) |

## SSL Certificate Error?

If you get an SSL error on Mac, run:
```bash
/Applications/Python*/Install\ Certificates.command
```
Or: `pip install certifi`

## Family Summary

| # | Family | Type | Markets | What to look for |
|---|---|---|---|---|
| 1 | US-Iran Ceasefire | deadline_nesting | 6 | Earlier deadline priced > later deadline |
| 2 | BTC March Upside | threshold_chain | 9 | Harder threshold priced > easier threshold |
| 3 | BTC March Downside | threshold_chain | 10 | Same as above but for dips |
| 4 | NBA Champion 2026 | mutually_exclusive | 26 | All team probs don't sum to 1.0 |
| 5 | Fed Rate Cut | deadline_nesting | 7 | Earlier meeting priced > later meeting |
