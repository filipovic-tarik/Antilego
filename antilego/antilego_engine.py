"""Top-level orchestration for Antilego collection and analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .contradiction_brain import analyze_snapshots, load_snapshots
from .market_discovery import discovery_report, write_discovery_report
from .market_tracking import run_collection
from .monitoring_registry import load_monitored_families, register_classified_events
from .paths import (
    DEFAULT_MONITORING_REGISTRY,
    DEFAULT_SNAPSHOT_PATH,
    live_snapshot_path,
)
from .relationship_intelligence import classify_relationship


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
    collect.add_argument("--output", type=Path)
    monitor = subparsers.add_parser(
        "monitor", help="snapshot approved discovered families every two minutes"
    )
    monitor.add_argument("--interval-minutes", type=float, default=2)
    monitor.add_argument(
        "--count", type=int, default=0, help="snapshots to collect; zero runs continuously"
    )
    monitor.add_argument("--output", type=Path)
    monitor.add_argument(
        "--monitoring-file", type=Path, default=DEFAULT_MONITORING_REGISTRY
    )
    classify = subparsers.add_parser(
        "classify", help="classify the relationship among supplied contracts"
    )
    classify.add_argument(
        "--input", type=Path, required=True, help="JSON file containing a contracts array"
    )
    classify.add_argument("--model", help="OpenAI model override")
    discover = subparsers.add_parser(
        "discover", help="discover currently tradable Polymarket contract groups"
    )
    discover.add_argument("--limit", type=int, default=10, help="maximum event groups")
    discover.add_argument(
        "--min-contracts", type=int, default=2, help="minimum contracts per group"
    )
    discover.add_argument(
        "--max-contracts", type=int, default=40, help="maximum contracts per group"
    )
    discover.add_argument("--page-size", type=int, default=100)
    discover.add_argument("--max-pages", type=int, default=10)
    discover.add_argument("--output", type=Path, help="optional JSON output file")
    discover.add_argument(
        "--classify",
        action="store_true",
        help="classify each discovered group with the configured OpenAI model",
    )
    discover.add_argument("--model", help="OpenAI model override for --classify")
    discover.add_argument(
        "--add-to-monitoring",
        action="store_true",
        help="persist approved classifications for the monitor command",
    )
    discover.add_argument(
        "--minimum-confidence",
        type=float,
        default=0.8,
        help="minimum confidence for automatic monitoring registration",
    )
    discover.add_argument(
        "--monitoring-file", type=Path, default=DEFAULT_MONITORING_REGISTRY
    )
    args = parser.parse_args()

    if args.command == "collect":
        run_collection(args.output)
        output_path = args.output if args.output is not None else live_snapshot_path()
        print(f"Saved one live snapshot to {output_path.resolve()}")
        return

    if args.command == "monitor":
        families = load_monitored_families(args.monitoring_file)
        if not families:
            parser.error(
                "No approved families are registered. Run discover with "
                "--classify --add-to-monitoring first."
            )
        output_path = args.output if args.output is not None else live_snapshot_path()
        print(
            f"Monitoring {len(families)} family/families every "
            f"{args.interval_minutes:g} minute(s). Press Ctrl+C to stop."
        )
        try:
            run_collection(
                output_path=args.output,
                interval_minutes=args.interval_minutes,
                count=args.count,
                families=families,
            )
        except KeyboardInterrupt:
            print("Monitoring stopped.")
        print(f"Snapshots saved to {output_path.resolve()}")
        return

    if args.command == "classify":
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        contracts = payload.get("contracts")
        if not isinstance(contracts, list):
            raise ValueError("Classification input must contain a contracts array")
        result = classify_relationship(contracts, model=args.model)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    if args.command == "discover":
        if args.add_to_monitoring and not args.classify:
            parser.error("--add-to-monitoring requires --classify")
        report = discovery_report(
            limit=args.limit,
            min_contracts=args.min_contracts,
            max_contracts=args.max_contracts,
            page_size=args.page_size,
            max_pages=args.max_pages,
        )
        if args.classify:
            for event in report["events"]:
                result = classify_relationship(event["contracts"], model=args.model)
                event["classification"] = result.to_dict()
        if args.add_to_monitoring:
            report["monitoring"] = register_classified_events(
                report["events"],
                registry_path=args.monitoring_file,
                minimum_confidence=args.minimum_confidence,
            )
        if args.output is not None:
            output_path = write_discovery_report(report, args.output)
            print(f"Discovered {report['candidate_count']} active group(s)")
            print(f"Saved to {output_path}")
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        return

    summary = analyze_archive(args.input)
    print(f"Snapshots: {summary['snapshot_count']}")
    print(f"Family evaluations: {summary['family_evaluations']}")
    for family, count in summary["violations_by_family"].items():
        print(f"{family}: {count} inconsistent snapshot(s)")


if __name__ == "__main__":
    main()
