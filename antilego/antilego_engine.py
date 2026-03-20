"""Top-level orchestration for Antilego collection and analysis."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .contradiction_brain import analyze_snapshots, load_snapshots
from .market_tracking import run_collection
from .paths import DEFAULT_SNAPSHOT_PATH


def analyze_archive(path: Path = DEFAULT_SNAPSHOT_PATH) -> dict:
    snapshots = load_snapshots(path)
    evaluations = analyze_snapshots(snapshots)
    violations_by_family = Counter(
        result["family"] for result in evaluations if result["coherent"] is False
    )
    return {
        "snapshot_count": len(snapshots),
        "family_evaluations": len(evaluations),
        "violations_by_family": dict(violations_by_family),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Antilego consistency engine")
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyze = subparsers.add_parser("analyze", help="analyze saved snapshots")
    analyze.add_argument("--input", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    collect = subparsers.add_parser("collect", help="collect public live prices")
    collect.add_argument("--output", type=Path, default=DEFAULT_SNAPSHOT_PATH)
    args = parser.parse_args()

    if args.command == "collect":
        run_collection(args.output)
        print(f"Saved one live snapshot to {args.output.resolve()}")
        return

    summary = analyze_archive(args.input)
    print(f"Snapshots: {summary['snapshot_count']}")
    print(f"Family evaluations: {summary['family_evaluations']}")
    for family, count in summary["violations_by_family"].items():
        print(f"{family}: {count} inconsistent snapshot(s)")


if __name__ == "__main__":
    main()
