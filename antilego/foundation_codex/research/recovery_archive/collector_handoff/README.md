# Important: Live-Price Collector and Historical Snapshots

This folder contains the exact recovered components requested:

- `snapshot_collector.py` is the script that polled live Polymarket CLOB midpoint prices and created/appended to `snapshots.jsonl`.
- `families.py` contains the market-family and asset-ID definitions required by the collector.
- `snapshots.jsonl` is the recovered historical output containing 132 timestamped snapshots.
- `requirements.txt` contains the minimal dependencies.

To collect prices every five minutes:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python snapshot_collector.py --loop 5
```

To preserve the historical dataset, rename it or use a different output path before starting a new collection:

```bash
python snapshot_collector.py --loop 5 --output new_snapshots.jsonl
```
