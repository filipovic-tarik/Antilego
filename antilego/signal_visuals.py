"""Shared output helpers for Antilego visualizations."""

from pathlib import Path

from .paths import weekly_figures_dir


def figure_path(filename: str, output_dir: Path | None = None) -> Path:
    """Return a stable destination for a generated figure."""
    output_dir = Path(output_dir) if output_dir is not None else weekly_figures_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename
