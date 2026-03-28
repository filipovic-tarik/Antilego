"""Canonical filesystem locations used throughout Antilego."""

from datetime import date, datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "archive"


def week_bounds(value: date | datetime | None = None) -> tuple[date, date]:
    """Return the Monday and Sunday containing ``value``."""
    if value is None:
        value = date.today()
    if isinstance(value, datetime):
        value = value.date()
    monday = value - timedelta(days=value.weekday())
    return monday, monday + timedelta(days=6)


def weekly_archive_dir(value: date | datetime | None = None) -> Path:
    """Return an archive path named with the week's Monday date."""
    monday, _ = week_bounds(value)
    return ARCHIVE_DIR / monday.isoformat()


def weekly_figures_dir(value: date | datetime | None = None) -> Path:
    return weekly_archive_dir(value) / "figures"


def weekly_market_data_dir(value: date | datetime | None = None) -> Path:
    return weekly_archive_dir(value) / "market_data"


def weekly_reports_dir(value: date | datetime | None = None) -> Path:
    return weekly_archive_dir(value) / "reports"


def live_snapshot_path(value: date | datetime | None = None) -> Path:
    return weekly_market_data_dir(value) / "snapshots.jsonl"


DEFAULT_SNAPSHOT_PATH = live_snapshot_path()


def ensure_output_directories(value: date | datetime | None = None) -> None:
    """Create the current weekly Antilego output directories."""
    for directory in (
        weekly_figures_dir(value),
        weekly_market_data_dir(value),
        weekly_reports_dir(value),
    ):
        directory.mkdir(parents=True, exist_ok=True)
