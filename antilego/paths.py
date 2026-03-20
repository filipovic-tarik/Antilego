"""Canonical filesystem locations used throughout Antilego."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MARKET_ARCHIVE_DIR = PROJECT_ROOT / "market_archive"
DEFAULT_SNAPSHOT_PATH = MARKET_ARCHIVE_DIR / "snapshots.jsonl"
INTELLIGENCE_REPORTS_DIR = PROJECT_ROOT / "intelligence_reports"
FIGURES_DIR = INTELLIGENCE_REPORTS_DIR / "figures" / "logos_v1"
REPORTS_DIR = INTELLIGENCE_REPORTS_DIR / "reports" / "logos_v1"


def ensure_output_directories() -> None:
    """Create the writable data and reporting directories when needed."""
    for directory in (MARKET_ARCHIVE_DIR, FIGURES_DIR, REPORTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)
