"""Deterministic probability-consistency laws used by Antilego."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .paths import DEFAULT_SNAPSHOT_PATH

ProbabilityLaw = Callable[[list[dict], float], list[dict]]


def _violation(left: str, right: str, magnitude: float, relation: str) -> dict:
    """Return the common violation representation used across all laws."""
    return {
        "left": left,
        "right": right,
        "pair": f"{left} {relation} {right}",
        "magnitude": magnitude,
    }


def check_deadline_monotonicity(markets: list[dict], tolerance: float) -> list[dict]:
    """Earlier-deadline probabilities cannot exceed later-deadline probabilities."""
    violations = []
    for earlier, later in zip(markets, markets[1:]):
        excess = float(earlier["price"]) - float(later["price"])
        if excess > tolerance:
            violations.append(
                _violation(earlier["label"], later["label"], excess, ">")
            )
    return violations


def check_threshold_monotonicity(markets: list[dict], tolerance: float) -> list[dict]:
    """Easier thresholds cannot be less likely than harder ordered thresholds."""
    violations = []
    for easier, harder in zip(markets, markets[1:]):
        excess = float(harder["price"]) - float(easier["price"])
        if excess > tolerance:
            violations.append(
                _violation(easier["label"], harder["label"], excess, "<")
            )
    return violations


def check_exhaustive_outcomes(markets: list[dict], tolerance: float) -> list[dict]:
    """Exactly-one-winner outcome probabilities must sum to one."""
    total = sum(float(market["price"]) for market in markets)
    deviation = total - 1.0
    if abs(deviation) <= tolerance + 1e-12:
        return []
    return [_violation("outcome sum", "1.0", abs(deviation), "≠")]


def check_complements(markets: list[dict], tolerance: float) -> list[dict]:
    """A proposition and its complement must sum to one."""
    total = sum(float(market["price"]) for market in markets)
    deviation = total - 1.0
    if abs(deviation) <= tolerance:
        return []
    return [_violation("complement sum", "1.0", abs(deviation), "≠")]


def check_mutual_exclusivity(markets: list[dict], tolerance: float) -> list[dict]:
    """Non-exhaustive outcomes that cannot co-occur may not sum above one."""
    total = sum(float(market["price"]) for market in markets)
    excess = total - 1.0
    if excess <= tolerance:
        return []
    return [_violation("exclusive outcome sum", "1.0", excess, ">")]


def check_logical_implication(markets: list[dict], tolerance: float) -> list[dict]:
    """For ordered A-implies-B pairs, P(A) cannot exceed P(B)."""
    violations = []
    for antecedent, consequent in zip(markets, markets[1:]):
        excess = float(antecedent["price"]) - float(consequent["price"])
        if excess > tolerance:
            violations.append(
                _violation(antecedent["label"], consequent["label"], excess, ">")
            )
    return violations


# This registry is the authoritative list of laws the active engine supports.
# ``mutually_exclusive`` remains as a compatibility alias for historical families
# that actually describe an exhaustive, exactly-one-winner outcome set.
PROBABILITY_LAWS: dict[str, ProbabilityLaw] = {
    "deadline_nesting": check_deadline_monotonicity,
    "threshold_chain": check_threshold_monotonicity,
    "exhaustive_outcomes": check_exhaustive_outcomes,
    "mutually_exclusive": check_exhaustive_outcomes,
    "complements": check_complements,
    "non_exhaustive_exclusivity": check_mutual_exclusivity,
    "logical_implication": check_logical_implication,
}

LAW_MARKET_REQUIREMENTS = {
    "complements": 2,
}

LAW_MINIMUM_MARKETS = {
    "deadline_nesting": 2,
    "threshold_chain": 2,
    "exhaustive_outcomes": 2,
    "mutually_exclusive": 2,
    "non_exhaustive_exclusivity": 2,
    "logical_implication": 2,
}

STRICT_ORDERING_LAWS = {
    "deadline_nesting",
    "threshold_chain",
    "logical_implication",
}


def evaluate_family(
    family: dict,
    exclusivity_tolerance: float = 0.005,
    exhaustive_tolerance: float = 0.03,
) -> dict:
    """Evaluate one market family using its registered probability law."""
    all_markets = family.get("markets", [])
    if family.get("pricing_mode") == "executable_order_book":
        return _evaluate_executable_family(
            family,
            exclusivity_tolerance=exclusivity_tolerance,
            exhaustive_tolerance=exhaustive_tolerance,
        )
    markets = [market for market in all_markets if market.get("price") is not None]
    family_type = family.get("type")

    if len(markets) != len(all_markets):
        return {
            "coherent": None,
            "data_complete": False,
            "violation_count": 0,
            "violations": [],
            "missing_prices": len(all_markets) - len(markets),
        }

    law = PROBABILITY_LAWS.get(family_type)
    if law is None:
        return {
            "coherent": None,
            "data_complete": True,
            "law_supported": False,
            "violation_count": 0,
            "violations": [],
            "error": f"Unsupported probability law: {family_type}",
        }

    required_count = LAW_MARKET_REQUIREMENTS.get(family_type)
    if required_count is not None and len(markets) != required_count:
        return {
            "coherent": None,
            "data_complete": True,
            "law_supported": True,
            "violation_count": 0,
            "violations": [],
            "error": f"{family_type} requires exactly {required_count} markets",
        }

    minimum_count = LAW_MINIMUM_MARKETS.get(family_type, 1)
    if len(markets) < minimum_count:
        return {
            "coherent": None,
            "data_complete": True,
            "law_supported": True,
            "violation_count": 0,
            "violations": [],
            "error": f"{family_type} requires at least {minimum_count} markets",
        }

    if family_type in STRICT_ORDERING_LAWS:
        law_tolerance = 0.0
    elif family_type in {"exhaustive_outcomes", "mutually_exclusive"}:
        law_tolerance = exhaustive_tolerance
    else:
        law_tolerance = exclusivity_tolerance
    violations = law(markets, law_tolerance)
    result = {
        "coherent": not violations,
        "data_complete": True,
        "law_supported": True,
        "violation_count": len(violations),
        "violations": violations,
    }
    if family_type in {
        "mutually_exclusive",
        "exhaustive_outcomes",
        "complements",
        "non_exhaustive_exclusivity",
    }:
        result["sum"] = sum(float(market["price"]) for market in markets)
    return result


def _executable_incomplete(markets: list[dict], required_fields: tuple[str, ...]) -> dict | None:
    missing = sum(
        1 for market in markets if any(market.get(field) is None for field in required_fields)
    )
    if not missing:
        return None
    statuses = {str(market.get("quote_status") or "unavailable") for market in markets}
    liquidity_status = "incomplete" if "unavailable" in statuses else "illiquid"
    return {
        "coherent": None,
        "data_complete": False,
        "law_supported": True,
        "liquidity_status": liquidity_status,
        "violation_count": 0,
        "violations": [],
        "missing_prices": missing,
    }


def _evaluate_executable_family(
    family: dict,
    *,
    exclusivity_tolerance: float,
    exhaustive_tolerance: float,
) -> dict:
    """Evaluate executable cross-book trades instead of non-tradable midpoints."""
    markets = family.get("markets", [])
    family_type = family.get("type")
    if family_type not in PROBABILITY_LAWS:
        return {
            "coherent": None,
            "data_complete": True,
            "law_supported": False,
            "liquidity_status": "incomplete",
            "violation_count": 0,
            "violations": [],
            "error": f"Unsupported probability law: {family_type}",
        }
    required_count = LAW_MARKET_REQUIREMENTS.get(family_type)
    minimum_count = LAW_MINIMUM_MARKETS.get(family_type, 1)
    if (required_count is not None and len(markets) != required_count) or len(markets) < minimum_count:
        return {
            "coherent": None,
            "data_complete": True,
            "law_supported": True,
            "liquidity_status": "incomplete",
            "violation_count": 0,
            "violations": [],
            "error": f"{family_type} has an invalid market count",
        }

    violations = []
    result_sum = None
    price_side = None
    if family_type in {"exhaustive_outcomes", "mutually_exclusive", "complements"}:
        incomplete = _executable_incomplete(markets, ("buy_price", "sell_price"))
        if incomplete:
            return incomplete
        buy_total = sum(float(market["buy_price"]) for market in markets)
        sell_total = sum(float(market["sell_price"]) for market in markets)
        buy_gap = 1.0 - buy_total
        sell_gap = sell_total - 1.0
        tolerance = exhaustive_tolerance if family_type in {"exhaustive_outcomes", "mutually_exclusive"} else exclusivity_tolerance
        if buy_gap > tolerance:
            violations.append(_violation("executable ask sum", "1.0", buy_gap, "<"))
        if sell_gap > tolerance:
            violations.append(_violation("executable bid sum", "1.0", sell_gap, ">"))
        if buy_gap >= sell_gap:
            result_sum, price_side = buy_total, "buy"
        else:
            result_sum, price_side = sell_total, "sell"
    elif family_type == "non_exhaustive_exclusivity":
        incomplete = _executable_incomplete(markets, ("sell_price",))
        if incomplete:
            return incomplete
        result_sum = sum(float(market["sell_price"]) for market in markets)
        price_side = "sell"
        excess = result_sum - 1.0
        if excess > exclusivity_tolerance:
            violations.append(_violation("executable bid sum", "1.0", excess, ">"))
    else:
        incomplete = _executable_incomplete(markets, ("buy_price", "sell_price"))
        if incomplete:
            return incomplete
        for left, right in zip(markets, markets[1:]):
            if family_type == "threshold_chain":
                excess = float(right["sell_price"]) - float(left["buy_price"])
                if excess > 0:
                    violations.append(_violation(left["label"], right["label"], excess, "<"))
            else:
                excess = float(left["sell_price"]) - float(right["buy_price"])
                if excess > 0:
                    violations.append(_violation(left["label"], right["label"], excess, ">"))

    result = {
        "coherent": not violations,
        "data_complete": True,
        "law_supported": True,
        "liquidity_status": "executable",
        "violation_count": len(violations),
        "violations": violations,
        "missing_prices": 0,
    }
    if result_sum is not None:
        result["sum"] = result_sum
        result["price_side"] = price_side
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
