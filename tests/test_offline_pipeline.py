import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from antilego.antilego_engine import analyze_archive
from antilego.market_tracking import (
    append_snapshot,
    collect_snapshot,
    executable_quote,
    fetch_order_book,
    run_collection,
)


class OfflinePipelineTests(unittest.TestCase):
    @patch("antilego.market_tracking.urllib.request.urlopen")
    def test_missing_clob_book_is_definitively_unexecutable(self, urlopen):
        urlopen.side_effect = HTTPError(
            "https://clob.polymarket.com/book",
            404,
            "Not Found",
            None,
            None,
        )
        book = fetch_order_book("missing-token")
        quote = executable_quote(book, 5)
        self.assertEqual(book["status"], "no_order_book")
        self.assertEqual(quote["quote_status"], "no_order_book")

    @patch("antilego.market_tracking.urllib.request.urlopen")
    def test_network_failure_remains_temporarily_unavailable(self, urlopen):
        urlopen.side_effect = TimeoutError("timed out")
        book = fetch_order_book("temporarily-unavailable-token")
        self.assertEqual(book["status"], "unavailable")

    def test_executable_quote_uses_depth_weighted_prices(self):
        quote = executable_quote(
            {
                "status": "book_available",
                "asks": [{"price": 0.4, "size": 3}, {"price": 0.5, "size": 4}],
                "bids": [{"price": 0.35, "size": 5}],
            },
            5,
        )
        self.assertAlmostEqual(quote["buy_price"], 0.44)
        self.assertAlmostEqual(quote["sell_price"], 0.35)
        self.assertEqual(quote["quote_status"], "executable")

    def test_empty_order_books_are_illiquid_instead_of_fifty_percent(self):
        family = {
            "name": "Empty books",
            "type": "exhaustive_outcomes",
            "constraint": "sum to one",
            "markets": [
                {"label": "A", "asset_id": "a"},
                {"label": "B", "asset_id": "b"},
            ],
        }
        empty_book = {
            "status": "empty_book",
            "bids": [],
            "asks": [],
            "min_order_size": 5,
        }
        result = collect_snapshot([family], lambda _asset_id: empty_book)["families"][0]
        self.assertIsNone(result["monitoring_key"])
        self.assertIsNone(result["coherent"])
        self.assertFalse(result["data_complete"])
        self.assertEqual(result["liquidity_status"], "illiquid")
        self.assertEqual(result["violation_count"], 0)

    def test_exhaustive_family_uses_executable_asks_and_bids(self):
        family = {
            "name": "Two outcomes",
            "type": "exhaustive_outcomes",
            "constraint": "sum to one",
            "markets": [
                {"label": "A", "asset_id": "a"},
                {"label": "B", "asset_id": "b"},
            ],
        }
        books = {
            "a": {
                "status": "book_available",
                "asks": [{"price": 0.42, "size": 10}],
                "bids": [{"price": 0.39, "size": 10}],
                "min_order_size": 5,
            },
            "b": {
                "status": "book_available",
                "asks": [{"price": 0.43, "size": 10}],
                "bids": [{"price": 0.4, "size": 10}],
                "min_order_size": 5,
            },
        }
        result = collect_snapshot([family], books.get)["families"][0]
        self.assertFalse(result["coherent"])
        self.assertEqual(result["liquidity_status"], "executable")
        self.assertAlmostEqual(result["sum"], 0.85)
        self.assertEqual(result["price_side"], "buy")
        self.assertAlmostEqual(result["buy_total"], 0.85)
        self.assertAlmostEqual(result["sell_total"], 0.79)

    def test_survival_deadline_uses_executable_reverse_ordering(self):
        family = {
            "name": "Continues through",
            "type": "survival_deadline_nesting",
            "constraint": "earlier >= later",
            "markets": [
                {"label": "October", "asset_id": "oct"},
                {"label": "November", "asset_id": "nov"},
            ],
        }
        books = {
            "oct": {
                "status": "book_available",
                "asks": [{"price": 0.72, "size": 10}],
                "bids": [{"price": 0.70, "size": 10}],
                "min_order_size": 5,
            },
            "nov": {
                "status": "book_available",
                "asks": [{"price": 0.62, "size": 10}],
                "bids": [{"price": 0.60, "size": 10}],
                "min_order_size": 5,
            },
        }
        result = collect_snapshot([family], books.get)["families"][0]
        self.assertTrue(result["coherent"])
        self.assertEqual(result["liquidity_status"], "executable")

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
