"""Read-only collection of executable Polymarket order-book prices."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .market_families import FAMILIES
from .paths import ensure_output_directories, live_snapshot_path

CLOB_BASE_URL = "https://clob.polymarket.com"
DEFAULT_EXECUTABLE_SHARES = 5.0
PriceFetcher = Callable[[str], float | dict | None]


def fetch_midpoint(token_id: str, timeout: float = 10) -> float | None:
    """Return a token's public CLOB midpoint, or ``None`` if unavailable."""
    query = urllib.parse.urlencode({"token_id": token_id})
    request = urllib.request.Request(
        f"{CLOB_BASE_URL}/midpoint?{query}",
        headers={"User-Agent": "Antilego/1.0 (read-only research)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        value = payload.get("mid", payload.get("price"))
        return float(value) if value is not None else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def fetch_order_book(token_id: str, timeout: float = 10) -> dict:
    """Return a normalized public CLOB order book for one outcome token."""
    query = urllib.parse.urlencode({"token_id": token_id})
    request = urllib.request.Request(
        f"{CLOB_BASE_URL}/book?{query}",
        headers={"User-Agent": "Antilego/1.0 (read-only research)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        bids = _normalize_levels(payload.get("bids"), reverse=True)
        asks = _normalize_levels(payload.get("asks"), reverse=False)
        minimum = float(payload.get("min_order_size") or DEFAULT_EXECUTABLE_SHARES)
        return {
            "status": "book_available" if bids or asks else "empty_book",
            "bids": bids,
            "asks": asks,
            "min_order_size": max(0.0, minimum),
            "book_timestamp": payload.get("timestamp"),
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {
            "status": "unavailable",
            "bids": [],
            "asks": [],
            "min_order_size": DEFAULT_EXECUTABLE_SHARES,
            "book_timestamp": None,
        }


def _normalize_levels(levels: object, *, reverse: bool) -> list[dict]:
    """Validate levels and sort best prices first."""
    normalized = []
    for level in levels if isinstance(levels, list) else []:
        if not isinstance(level, dict):
            continue
        try:
            price = float(level["price"])
            size = float(level["size"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= price <= 1 and size > 0:
            normalized.append({"price": price, "size": size})
    return sorted(normalized, key=lambda level: level["price"], reverse=reverse)


def _vwap(levels: list[dict], shares: float) -> tuple[float | None, float]:
    """Return the executable average price and available depth for a share size."""
    remaining = shares
    cost = 0.0
    available = sum(float(level["size"]) for level in levels)
    for level in levels:
        filled = min(remaining, float(level["size"]))
        cost += filled * float(level["price"])
        remaining -= filled
        if remaining <= 1e-12:
            return cost / shares, available
    return None, available


def executable_quote(book: dict, shares: float) -> dict:
    """Calculate depth-aware buy and sell prices for the requested share size."""
    buy_price, ask_depth = _vwap(book.get("asks", []), shares)
    sell_price, bid_depth = _vwap(book.get("bids", []), shares)
    status = str(book.get("status") or "unavailable")
    if status != "unavailable":
        if buy_price is not None and sell_price is not None:
            status = "executable"
        elif book.get("bids") or book.get("asks"):
            status = "illiquid"
        else:
            status = "empty_book"
    return {
        "buy_price": buy_price,
        "sell_price": sell_price,
        "best_ask": book.get("asks", [{}])[0].get("price") if book.get("asks") else None,
        "best_bid": book.get("bids", [{}])[0].get("price") if book.get("bids") else None,
        "ask_depth": ask_depth,
        "bid_depth": bid_depth,
        "quote_status": status,
        "book_timestamp": book.get("book_timestamp"),
    }


def collect_snapshot(
    families: Iterable[dict] = FAMILIES,
    fetcher: PriceFetcher = fetch_order_book,
    executable_shares: float = DEFAULT_EXECUTABLE_SHARES,
) -> dict:
    """Collect and evaluate one timestamped snapshot of the supplied families."""
    from .contradiction_brain import evaluate_family

    families = list(families)
    asset_ids = list(
        dict.fromkeys(
            market["asset_id"]
            for family in families
            for market in family["markets"]
        )
    )
    if fetcher is fetch_order_book:
        with ThreadPoolExecutor(max_workers=min(12, max(1, len(asset_ids)))) as pool:
            fetched = dict(zip(asset_ids, pool.map(fetcher, asset_ids)))
    else:
        fetched = {asset_id: fetcher(asset_id) for asset_id in asset_ids}

    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(), "families": []}
    for family in families:
        raw_quotes = [fetched[market["asset_id"]] for market in family["markets"]]
        books = [quote for quote in raw_quotes if isinstance(quote, dict)]
        target_shares = max(
            [executable_shares]
            + [float(book.get("min_order_size") or 0) for book in books]
        )
        markets = []
        for market, raw_quote in zip(family["markets"], raw_quotes):
            if isinstance(raw_quote, dict):
                quote = executable_quote(raw_quote, target_shares)
                price = quote["buy_price"]
            else:
                # Preserve custom/offline fetchers and historical callers.
                price = float(raw_quote) if raw_quote is not None else None
                quote = {
                    "buy_price": price,
                    "sell_price": price,
                    "best_ask": price,
                    "best_bid": price,
                    "ask_depth": None,
                    "bid_depth": None,
                    "quote_status": "executable" if price is not None else "unavailable",
                    "book_timestamp": None,
                }
            markets.append(
                {
                    "label": market["label"],
                    "asset_id": market["asset_id"],
                    "price": price,
                    **quote,
                }
            )
        family_result = {
            "name": family["name"],
            "type": family["type"],
            "constraint": family["constraint"],
            "pricing_mode": "executable_order_book",
            "target_shares": target_shares,
            "markets": markets,
        }
        family_result.update(evaluate_family(family_result))
        snapshot["families"].append(family_result)
    return snapshot


def append_snapshot(snapshot: dict, output_path: Path | None = None) -> Path:
    """Append one snapshot to JSONL and return the resolved output path."""
    output_path = Path(output_path) if output_path is not None else live_snapshot_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(snapshot, separators=(",", ":")) + "\n")
    return output_path.resolve()


def run_collection(
    output_path: Path | None = None,
    interval_minutes: float = 0,
    count: int = 1,
    families: Iterable[dict] | None = None,
    fetcher: PriceFetcher = fetch_order_book,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[dict]:
    """Collect one or more snapshots; ``count=0`` continues until interrupted."""
    if interval_minutes < 0 or count < 0:
        raise ValueError("interval_minutes and count cannot be negative")
    ensure_output_directories()
    output_path = Path(output_path) if output_path is not None else live_snapshot_path()
    families = FAMILIES if families is None else list(families)
    collected = []
    iteration = 0
    while count == 0 or iteration < count:
        snapshot = collect_snapshot(families, fetcher)
        append_snapshot(snapshot, output_path)
        if count == 0:
            collected[:] = [snapshot]
        else:
            collected.append(snapshot)
        iteration += 1
        if count != 0 and iteration >= count:
            break
        if interval_minutes <= 0:
            break
        sleeper(interval_minutes * 60)
    return collected


def main() -> None:
    parser = argparse.ArgumentParser(description="Antilego public market collector")
    parser.add_argument("--loop", type=float, default=0, metavar="MINUTES")
    parser.add_argument("-n", "--count", type=int, default=1)
    parser.add_argument("-o", "--output", type=Path)
    args = parser.parse_args()
    try:
        snapshots = run_collection(args.output, args.loop, args.count)
    except KeyboardInterrupt:
        print("Collection stopped.")
        return
    for snapshot in snapshots:
        violations = sum(
            family["violation_count"] for family in snapshot["families"]
        )
        print(f"{snapshot['timestamp']}: {violations} violation(s)")
    output_path = args.output if args.output is not None else live_snapshot_path()
    print(f"Saved to {output_path.resolve()}")


if __name__ == "__main__":
    main()
