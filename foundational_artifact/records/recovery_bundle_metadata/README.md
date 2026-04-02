# LOGOS Complete Organized Bundle

Prepared on August 4, 2026.

## What this is

LOGOS stands for **Logical Optimization for Global Outcome Systems**. The project studies logical incoherence across related Polymarket prediction-market contracts and projects observed prices onto a nearest coherent probability system using convex optimization.

The verified V1 prototype covers 132 snapshots collected over approximately 11 hours, 58 contracts, five market families, and 7,656 observations.

## Start here

If your immediate goal is to find the script that collected the live prices and created `snapshots.jsonl`, open:

`01_RUNNABLE_SNAPSHOT_COLLECTOR/snapshot_collector.py`

It requires `families.py` in the same directory. Detailed commands are in `01_RUNNABLE_SNAPSHOT_COLLECTOR/RUN_INSTRUCTIONS.md`.

The collected dataset is:

`02_COLLECTED_DATA/snapshots.jsonl`

The most complete analysis notebook is:

`03_COMPLETE_ANALYSIS/LOGOS_V1_Analysis_COMPLETE.ipynb`

## Folder map

- `00_START_HERE`: bundle guide, source notes, file index, and checksums.
- `01_RUNNABLE_SNAPSHOT_COLLECTOR`: the price collector, market definitions, asset-ID helper, and experimental websocket files.
- `02_COLLECTED_DATA`: the primary 132-snapshot JSONL dataset.
- `03_COMPLETE_ANALYSIS`: completed notebook, Python analysis, HTML/PDF output, figures, and earlier notebook versions.
- `04_MARKET_FAMILY_SPREADSHEETS`: Ceasefire, BTC, NBA Champion, and Fed Rate Cut family definitions.
- `05_WRITEUPS_AND_REPORTS`: current brief, build plan, project write-up, and V1 PDFs.
- `06_PROPOSALS_PROTOTYPE_AND_V2`: every recovered scholarship proposal, prototype memo, and V2 expansion revision.
- `07_EARLY_POLYMARKET_EXPLORATION`: the earliest recovered Polymarket exploration notebook and environment information.
- `08_ORIGINAL_ZIP_ARCHIVES`: the original starter-kit and complete-analysis ZIP files.
- `90_ALL_FOUND_VERSIONS`: recovery-oriented copies organized by their original source location. This intentionally contains duplicates.

## Which files are canonical?

For running the collector, use section `01`.

For the historical data, use section `02`.

For analysis and figures, use section `03`.

For a complete recovery record, consult section `90` and the checksum/index files in this folder.

## Important distinction

`snapshot_collector.py` is the script that actually polled public CLOB midpoint-price endpoints and appended timestamped records to `snapshots.jsonl`.

`experimental_websocket_live.py` is a separate experimental authenticated websocket/order-book example. It is not the script that produced the recovered JSONL dataset, and it still contains credential placeholders.

## Exclusions

The original `/Users/calebmukasa/logos/.venv` directory was intentionally excluded. It was roughly 573 MB with the surrounding environment and contained reinstallable third-party packages, not unique project work.

System caches, `__pycache__`, `.DS_Store`, Git internals, Anaconda file-browser databases, unrelated ChatGPT handoff material, and unrelated files that merely contained words such as “logical” or “prediction” were also excluded from the curated sections. Relevant source copies and notebook checkpoints are retained in section `90` where useful.

No original files were moved, renamed, or deleted while creating this bundle.
