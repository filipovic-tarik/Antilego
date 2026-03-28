# Verification Report

Verification completed on August 4, 2026 before ZIP creation.

## Essential collector package

- `snapshot_collector.py` and `families.py` compile successfully with Python 3.
- The collector identifies `snapshots.jsonl` as its default output file.
- The collector supports one-shot, timed-loop, fixed-count, and custom-output modes.
- The collector uses Polymarket's public CLOB midpoint endpoint and does not require an API key.

## Historical dataset

- JSONL parsing: passed.
- Snapshot count: 132.
- Families in the first snapshot: 5.
- Market records in the first snapshot: 58.
- First timestamp: `2026-03-15T03:37:41.333611+00:00`.
- Last timestamp: `2026-03-15T16:00:55.598207+00:00`.
- SHA-256: `c4ef3a7f6470113729ebd986058af9c9692ee8772f2969330aa301d3f7f0accf`.

All four recovered copies of `snapshots.jsonl` have the same SHA-256 value and are byte-for-byte identical.

## Other formats

- Jupyter notebook JSON validation: passed for all actual notebooks. Files inside `.virtual_documents` are Python-text projections despite retaining an `.ipynb` filename and were validated as recovery artifacts rather than notebook JSON.
- DOCX and XLSX ZIP-container integrity: passed.
- Original project ZIP integrity: passed.
- Cloud-placeholder recovery: passed; every file copied from the organized Documents archive is nonempty in this bundle.

## Preservation

The package contains curated working copies plus recovery-oriented source-location copies. Original files on the laptop were not modified or removed.
