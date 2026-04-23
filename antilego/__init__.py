"""Antilego: probability-consistency research for prediction markets."""

from .contradiction_brain import (
    PROBABILITY_LAWS,
    analyze_snapshots,
    evaluate_family,
    load_snapshots,
)

__all__ = [
    "PROBABILITY_LAWS",
    "analyze_snapshots",
    "evaluate_family",
    "load_snapshots",
]
