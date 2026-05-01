import json
import tempfile
import unittest
from pathlib import Path

from antilego.antilego_engine import analyze_archive
from antilego.market_tracking import append_snapshot, collect_snapshot, run_collection


class OfflinePipelineTests(unittest.TestCase):
    def test_collect_save_load_and_analyze(self):
        families = [
            {
                "name": "Fed Rate Cut",
                "type": "deadline_nesting",
                "constraint": "earlier <= later",
                "markets": [
                    {"label": "September", "asset_id": "sep"},
                    {"label": "October", "asset_id": "oct"},
                ],
            }
        ]
        prices = {"sep": 0.75, "oct": 0.63}
        snapshot = collect_snapshot(families, prices.get)

        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "snapshots.jsonl"
            append_snapshot(snapshot, archive)
            raw = json.loads(archive.read_text(encoding="utf-8"))
            self.assertEqual(raw["families"][0]["violation_count"], 1)

            summary = analyze_archive(archive)
            self.assertEqual(summary["snapshot_count"], 1)
            self.assertEqual(summary["violations_by_family"], {"Fed Rate Cut": 1})

    def test_monitoring_loop_uses_supplied_families_and_five_minute_interval(self):
        families = [
            {
                "name": "Live family",
                "type": "deadline_nesting",
                "constraint": "earlier <= later",
                "markets": [
                    {"label": "Earlier", "asset_id": "early"},
                    {"label": "Later", "asset_id": "late"},
                ],
            }
        ]
        prices = {"early": 0.4, "late": 0.6}
        sleeps = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "snapshots.jsonl"
            snapshots = run_collection(
                output_path=output,
                interval_minutes=5,
                count=2,
                families=families,
                fetcher=prices.get,
                sleeper=sleeps.append,
            )
            saved = output.read_text(encoding="utf-8").splitlines()

        self.assertEqual(len(snapshots), 2)
        self.assertEqual(len(saved), 2)
        self.assertEqual(sleeps, [300])


if __name__ == "__main__":
    unittest.main()
