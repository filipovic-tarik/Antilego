"""Optional read-only live smoke test.

Run explicitly with ``ANTILEGO_LIVE_TEST=1 python -m unittest
tests.test_live_polymarket``. It is skipped during normal offline test runs.
"""

import json
import os
import unittest
import urllib.request

from antilego.market_discovery import discover_active_market_groups
from antilego.market_tracking import collect_snapshot, fetch_order_book


@unittest.skipUnless(os.environ.get("ANTILEGO_LIVE_TEST") == "1", "live test disabled")
class LivePolymarketTests(unittest.TestCase):
    def test_active_market_has_public_order_book(self):
        request = urllib.request.Request(
            "https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=1",
            headers={"User-Agent": "Antilego/1.0 (read-only research)"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            market = json.loads(response.read().decode("utf-8"))[0]
        token_ids = market["clobTokenIds"]
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
        family = {
            "name": "Live smoke test",
            "type": "threshold_chain",
            "constraint": "single-market connectivity check",
            "markets": [{"label": market["question"], "asset_id": token_ids[0]}],
        }
        snapshot = collect_snapshot([family])
        market_result = snapshot["families"][0]["markets"][0]
        self.assertIn(market_result["quote_status"], {"executable", "illiquid", "empty_book"})

    def test_discovers_current_tradable_contract_group(self):
        groups = discover_active_market_groups(
            limit=1,
            page_size=25,
            max_pages=4,
        )
        self.assertEqual(len(groups), 1)
        self.assertGreaterEqual(len(groups[0]["contracts"]), 2)
        self.assertTrue(all(contract["asset_id"] for contract in groups[0]["contracts"]))
        books = [
            fetch_order_book(contract["asset_id"])
            for contract in groups[0]["contracts"][:5]
        ]
        self.assertTrue(any(book["status"] != "unavailable" for book in books))


if __name__ == "__main__":
    unittest.main()
