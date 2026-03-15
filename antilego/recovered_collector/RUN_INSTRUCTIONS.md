# Running the LOGOS Snapshot Collector

## Files used by the historical collection

- `snapshot_collector.py`: polls current Polymarket CLOB midpoint prices and appends one JSON object per snapshot.
- `families.py`: defines the five logical market families and their token/asset IDs.
- `requirements.txt`: minimal Python dependencies for the collector.

## Set up

Open Terminal in this directory and create an isolated environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Take one snapshot

```bash
python snapshot_collector.py
```

By default, this creates or appends to `snapshots.jsonl` in the current directory.

## Collect every five minutes until stopped

```bash
python snapshot_collector.py --loop 5
```

Stop cleanly with `Ctrl+C`.

## Collect exactly 100 snapshots at five-minute intervals

```bash
python snapshot_collector.py --loop 5 -n 100
```

## Write to another file

```bash
python snapshot_collector.py --loop 5 --output new_snapshots.jsonl
```

## API and credentials

The collector uses Polymarket's public CLOB midpoint endpoint and does not require an API key. The separate `experimental_websocket_live.py` example is not needed for JSONL collection and should not be used without reviewing its authentication and credential handling.

## Historical dataset

Do not overwrite the preserved historical dataset in `../02_COLLECTED_DATA/snapshots.jsonl`. Run new collection from this directory or specify a new output filename.
