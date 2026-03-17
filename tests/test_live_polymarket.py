"""Optional read-only live smoke test.

Run explicitly with ``ANTILEGO_LIVE_TEST=1 python -m unittest
tests.test_live_polymarket``. It is skipped during normal offline test runs.
"""

import json
import os
import unittest
import urllib.request

from antilego.market_tracking import collect_snapshot


@unittest.skipUnless(os.environ.get("ANTILEGO_LIVE_TEST") == "1", "live test disabled")
class LivePolymarketTests(unittest.TestCase):
    def test_active_market_has_public_midpoint(self):
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
        midpoint = snapshot["families"][0]["markets"][0]["price"]
        self.assertIsNotNone(midpoint)
        self.assertGreaterEqual(midpoint, 0.0)
        self.assertLessEqual(midpoint, 1.0)


if __name__ == "__main__":
    unittest.main()
