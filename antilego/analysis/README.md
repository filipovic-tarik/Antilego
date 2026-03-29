# Antilego analysis workspace

This directory contains Antilego's independent analysis baseline.

- `antilego_analysis.py` is the executable analysis and visualization workflow.
- `ANTILEGO_Analysis.ipynb` is its exploratory notebook counterpart.

These files are active Antilego material and may be redesigned freely. They read
the current weekly snapshot archive and write figures into that same week's
`figures/` directory. A complete market family is required before it is included
in analysis, preventing missing live prices from being treated as valid evidence.
