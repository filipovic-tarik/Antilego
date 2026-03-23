"""Read-only collection of public Polymarket midpoint prices."""

from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .market_families import FAMILIES
from .paths import ensure_output_directories, live_snapshot_path

CLOB_BASE_URL = "https://clob.polymarket.com"
PriceFetcher = Callable[[str], float | None]


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


def collect_snapshot(
    families: Iterable[dict] = FAMILIES,
    fetcher: PriceFetcher = fetch_midpoint,
) -> dict:
    """Collect and evaluate one timestamped snapshot of the supplied families."""
    from .contradiction_brain import evaluate_family

    snapshot = {"timestamp": datetime.now(timezone.utc).isoformat(), "families": []}
    for family in families:
        family_result = {
            "name": family["name"],
            "type": family["type"],
            "constraint": family["constraint"],
            "markets": [
                {
                    "label": market["label"],
                    "asset_id": market["asset_id"],
                    "price": fetcher(market["asset_id"]),
                }
                for market in family["markets"]
            ],
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
) -> list[dict]:
    """Collect one or more snapshots; ``count=0`` continues until interrupted."""
    ensure_output_directories()
    output_path = Path(output_path) if output_path is not None else live_snapshot_path()
    collected = []
    iteration = 0
    while count == 0 or iteration < count:
        snapshot = collect_snapshot()
        append_snapshot(snapshot, output_path)
        collected.append(snapshot)
        iteration += 1
        if count != 0 and iteration >= count:
            break
        if interval_minutes <= 0:
            break
        time.sleep(interval_minutes * 60)
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
