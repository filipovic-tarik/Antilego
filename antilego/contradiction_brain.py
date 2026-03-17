"""Probability-consistency rules used by Antilego."""

from __future__ import annotations

import json
from pathlib import Path

from .paths import DEFAULT_SNAPSHOT_PATH


def evaluate_family(family: dict, exclusivity_tolerance: float = 0.005) -> dict:
    """Evaluate one family and describe every detected probability violation."""
    all_markets = family.get("markets", [])
    markets = [market for market in all_markets if market.get("price") is not None]
    prices = [float(market["price"]) for market in markets]
    family_type = family.get("type")
    violations = []

    if len(markets) != len(all_markets):
        return {
            "coherent": None,
            "data_complete": False,
            "violation_count": 0,
            "violations": [],
            "missing_prices": len(all_markets) - len(markets),
        }

    if family_type in {"deadline_nesting", "threshold_chain"}:
        for left, right in zip(markets, markets[1:]):
            left_price, right_price = float(left["price"]), float(right["price"])
            invalid = (
                left_price > right_price
                if family_type == "deadline_nesting"
                else left_price < right_price
            )
            if invalid:
                violations.append(
                    {
                        "left": left["label"],
                        "right": right["label"],
                        "magnitude": abs(left_price - right_price),
                    }
                )
    elif family_type == "mutually_exclusive" and prices:
        total = sum(prices)
        deviation = total - 1.0
        if abs(deviation) > exclusivity_tolerance:
            violations.append(
                {"left": "outcome sum", "right": "1.0", "magnitude": abs(deviation)}
            )

    result = {
        "coherent": not violations,
        "data_complete": True,
        "violation_count": len(violations),
        "violations": violations,
    }
    if family_type == "mutually_exclusive":
        result["sum"] = sum(prices)
    return result


def load_snapshots(path: Path = DEFAULT_SNAPSHOT_PATH) -> list[dict]:
    """Load snapshots from the canonical JSONL archive."""
    with Path(path).open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def analyze_snapshots(snapshots: list[dict]) -> list[dict]:
    """Re-evaluate saved snapshots using the current consistency rules."""
    results = []
    for snapshot in snapshots:
        for family in snapshot.get("families", []):
            evaluation = evaluate_family(family)
            results.append(
                {
                    "timestamp": snapshot.get("timestamp"),
                    "family": family.get("name"),
                    "family_type": family.get("type"),
                    **evaluation,
                }
            )
    return results
