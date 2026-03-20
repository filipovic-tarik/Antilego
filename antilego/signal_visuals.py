"""Shared output helpers for Antilego visualizations."""

from pathlib import Path

from .paths import FIGURES_DIR


def figure_path(filename: str, output_dir: Path = FIGURES_DIR) -> Path:
    """Return a stable destination for a generated figure."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / filename
