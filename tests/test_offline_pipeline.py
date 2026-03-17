import json
import tempfile
import unittest
from pathlib import Path

from antilego.antilego_engine import analyze_archive
from antilego.market_tracking import append_snapshot, collect_snapshot


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


if __name__ == "__main__":
    unittest.main()
