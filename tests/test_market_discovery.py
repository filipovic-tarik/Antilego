import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from antilego import market_discovery
from antilego.market_discovery import (
    candidate_from_event,
    contract_from_market,
    discover_active_market_groups,
    discovery_report,
    write_discovery_report,
    fetch_active_events,
)


def market(
    market_id: str,
    *,
    active: bool = True,
    closed: bool = False,
    accepting_orders: bool = True,
    outcomes: object = '["Yes", "No"]',
    token_ids: object | None = None,
) -> dict:
    token_ids = token_ids or json.dumps([f"yes-{market_id}", f"no-{market_id}"])
    return {
        "id": market_id,
        "question": f"Will outcome {market_id} happen?",
        "description": f"Resolution rules for {market_id}",
        "groupItemTitle": f"Outcome {market_id}",
        "slug": f"outcome-{market_id}",
        "active": active,
        "closed": closed,
        "acceptingOrders": accepting_orders,
        "enableOrderBook": True,
        "outcomes": outcomes,
        "clobTokenIds": token_ids,
        "volume24hr": float(market_id) if market_id.isdigit() else 0,
    }


class ActiveMarketDiscoveryTests(unittest.TestCase):
    def test_gamma_fetch_retries_transient_network_failure(self):
        calls = 0

        class FakeResponse(BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(_request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("temporary DNS failure")
            return FakeResponse(b"[]")

        with (
            patch.object(market_discovery.urllib.request, "urlopen", fake_urlopen),
            patch.object(market_discovery.time, "sleep"),
        ):
            result = fetch_active_events(limit=1)

        self.assertEqual(result, [])
        self.assertEqual(calls, 2)

    def test_contract_uses_yes_token_and_rejects_untradable_markets(self):
        contract = contract_from_market(
            market("7", outcomes=["No", "Yes"], token_ids=["no-7", "yes-7"])
        )
        self.assertEqual(contract["asset_id"], "yes-7")
        self.assertEqual(contract["label"], "Outcome 7")
        self.assertIsNone(contract_from_market(market("8", closed=True)))
        self.assertIsNone(contract_from_market(market("9", accepting_orders=False)))
        self.assertIsNone(
            contract_from_market(market("10", outcomes='["Team A", "Team B"]'))
        )

    def test_event_candidate_filters_and_ranks_contracts(self):
        event = {
            "id": "event-1",
            "slug": "event-one",
            "title": "Event One",
            "volume24hr": "123.5",
            "markets": [market("1"), market("3"), market("2", closed=True)],
        }
        candidate = candidate_from_event(event)
        self.assertEqual(candidate["event_id"], "event-1")
        self.assertEqual([item["id"] for item in candidate["contracts"]], ["3", "1"])

    def test_discovery_pages_until_it_finds_enough_groups(self):
        pages = {
            0: [{"id": "single", "title": "Single", "markets": [market("1")]}],
            1: [
                {
                    "id": "candidate",
                    "title": "Candidate",
                    "markets": [market("2"), market("3")],
                }
            ],
        }
        calls = []

        def fetcher(limit: int, offset: int) -> list[dict]:
            calls.append((limit, offset))
            return pages.get(offset, [])

        candidates = discover_active_market_groups(
            limit=1,
            page_size=1,
            max_pages=3,
            fetcher=fetcher,
        )
        self.assertEqual([candidate["event_id"] for candidate in candidates], ["candidate"])
        self.assertEqual(calls, [(1, 0), (1, 1)])

    def test_report_can_be_written_as_json(self):
        def fetcher(limit: int, offset: int) -> list[dict]:
            if offset:
                return []
            return [
                {
                    "id": "candidate",
                    "title": "Candidate",
                    "markets": [market("1"), market("2")],
                }
            ]

        report = discovery_report(limit=1, page_size=2, fetcher=fetcher)
        with tempfile.TemporaryDirectory() as directory:
            output = write_discovery_report(report, Path(directory) / "active.json")
            restored = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(restored["candidate_count"], 1)
        self.assertEqual(restored["events"][0]["event_id"], "candidate")


if __name__ == "__main__":
    unittest.main()
