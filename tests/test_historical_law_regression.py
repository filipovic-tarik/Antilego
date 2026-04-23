import unittest
from collections import Counter
from pathlib import Path

from antilego.contradiction_brain import analyze_snapshots, load_snapshots


class HistoricalLawRegressionTests(unittest.TestCase):
    def test_march_2026_violation_counts_remain_stable(self):
        fixture = Path(__file__).parent / "fixtures" / "march_2026_snapshots.jsonl"
        results = analyze_snapshots(load_snapshots(fixture))
        counts = Counter(
            result["family"] for result in results if result["violation_count"] > 0
        )

        self.assertEqual(
            counts,
            {
                "BTC March Upside": 65,
                "BTC March Downside": 132,
                "2026 NBA Champion": 132,
                "Fed Rate Cut": 132,
            },
        )


if __name__ == "__main__":
    unittest.main()
