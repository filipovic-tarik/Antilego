# Weekly output archive

Antilego creates one output directory for each Monday–Sunday week:

```text
archive/
└── YYYY-MM-DD/
    ├── figures/
    ├── market_data/
    └── reports/
```

Each weekly folder is named after its Monday. For example, outputs produced from
August 3 through August 9, 2026 are stored in `archive/2026-08-03/`. A week that
begins Monday, August 31 remains under `archive/2026-08-31/`, even when its later
days fall in September.
