import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from antilego.dashboard import (
    DEFAULT_SNAPSHOT_INTERVAL_MINUTES,
    DashboardServer,
    DashboardState,
    _next_cadence_start,
    _partition_executable_families,
    _polymarket_event_url,
    _snapshot_history,
)


class StubState:
    def __init__(self):
        self.connected = False

    def status(self):
        return {
            "chatgpt": {
                "connected": self.connected,
                "email": None,
                "message": "Connected" if self.connected else "Not connected",
            },
            "monitor": {"state": "stopped"},
            "discovery": {"state": "idle"},
            "graphs": {"state": "idle", "items": []},
            "monitored_families": [],
            "family_count": 0,
        }

    def begin_chatgpt_connection(self, redirect_uri):
        self.redirect_uri = redirect_uri
        return "https://auth.openai.com/example"


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.state = StubState()
        self.server = DashboardServer(("127.0.0.1", 0), self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_dashboard_and_status_are_served_locally(self):
        with urlopen(f"{self.base_url}/", timeout=2) as response:
            page = response.read().decode("utf-8")
        with urlopen(f"{self.base_url}/api/status", timeout=2) as response:
            status = json.load(response)

        self.assertIn("Antilego", page)
        self.assertEqual(status["family_count"], 0)
        self.assertEqual(status["csrf_token"], self.server.csrf_token)

    def test_chatgpt_connection_requires_the_local_csrf_token(self):
        body = b"{}"
        rejected = Request(
            f"{self.base_url}/api/chatgpt/connect",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as caught:
            urlopen(rejected, timeout=2)
        self.assertEqual(caught.exception.code, 403)

        accepted = Request(
            f"{self.base_url}/api/chatgpt/connect",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Antilego-Token": self.server.csrf_token,
            },
            method="POST",
        )
        with urlopen(accepted, timeout=2) as response:
            payload = json.load(response)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["authorization_url"], "https://auth.openai.com/example")
        self.assertEqual(
            self.state.redirect_uri,
            f"{self.base_url}/auth/callback",
        )


class DashboardStateTests(unittest.TestCase):
    def test_polymarket_event_url_uses_the_discovered_event_slug(self):
        family = {"source": {"event_slug": "fed decision / october"}}
        self.assertEqual(
            _polymarket_event_url(family),
            "https://polymarket.com/event/fed%20decision%20%2F%20october",
        )
        self.assertIsNone(_polymarket_event_url({"source": {}}))

    def test_default_snapshot_interval_is_three_minutes(self):
        self.assertEqual(DEFAULT_SNAPSHOT_INTERVAL_MINUTES, 3.0)

    def test_fixed_cadence_accounts_for_collection_time(self):
        self.assertEqual(_next_cadence_start(100.0, 180.0, 156.0), 280.0)
        self.assertEqual(_next_cadence_start(100.0, 180.0, 301.0), 460.0)

    def test_liquidity_partition_only_drops_confirmed_illiquid_families(self):
        families = [
            {"monitoring_key": "a", "name": "A"},
            {"monitoring_key": "b", "name": "B"},
            {"monitoring_key": "c", "name": "C"},
        ]
        snapshot = {"families": [
            {"monitoring_key": "a", "name": "A", "liquidity_status": "executable"},
            {"monitoring_key": "b", "name": "B", "liquidity_status": "illiquid"},
            {"monitoring_key": "c", "name": "C", "liquidity_status": "incomplete"},
        ]}
        executable, illiquid, unknown = _partition_executable_families(
            families, snapshot
        )
        self.assertEqual([family["name"] for family in executable], ["A"])
        self.assertEqual([family["name"] for family in illiquid], ["B"])
        self.assertEqual([family["name"] for family in unknown], ["C"])

    def test_empty_selection_does_not_approve_everything(self):
        state = DashboardState()
        state.pending_events = [{"event_id": "event-1", "approval_eligible": True}]
        with self.assertRaisesRegex(ValueError, "Select at least one"):
            state.approve_discovery([])

    def test_approval_registers_only_families_with_executable_quotes(self):
        def event(event_id):
            return {
                "event_id": event_id,
                "event_slug": event_id,
                "title": event_id.title(),
                "approval_eligible": True,
                "classification": {
                    "relationship_found": True,
                    "law": "deadline_nesting",
                    "ordered_contract_ids": [f"{event_id}-early", f"{event_id}-late"],
                    "confidence": 0.95,
                    "requires_review": False,
                    "reason": "Nested deadlines",
                },
                "contracts": [
                    {
                        "id": f"{event_id}-early",
                        "label": "Early",
                        "asset_id": f"{event_id}-early-asset",
                    },
                    {
                        "id": f"{event_id}-late",
                        "label": "Late",
                        "asset_id": f"{event_id}-late-asset",
                    },
                ],
            }

        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "monitoring.json"
            state = DashboardState()
            state.pending_events = [event("liquid"), event("dry")]
            snapshot = {
                "families": [
                    {
                        "monitoring_key": "polymarket:event:liquid",
                        "name": "Liquid",
                        "liquidity_status": "executable",
                    },
                    {
                        "monitoring_key": "polymarket:event:dry",
                        "name": "Dry",
                        "liquidity_status": "illiquid",
                    },
                ]
            }
            with (
                patch("antilego.dashboard.DEFAULT_MONITORING_REGISTRY", registry),
                patch("antilego.dashboard.collect_snapshot", return_value=snapshot),
            ):
                result = state.approve_discovery()
            payload = json.loads(registry.read_text(encoding="utf-8"))

        self.assertEqual(result["accepted"], ["polymarket:event:liquid"])
        self.assertEqual(result["unexecutable"], ["dry"])
        self.assertEqual([family["name"] for family in payload["families"]], ["Liquid"])
        self.assertEqual(state.pending_events, [])

    def test_clear_all_resets_dashboard_without_deleting_archive_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "archive" / "current-week"
            registry = root / "monitoring" / "monitored_families.json"
            discovery = root / "monitoring" / "latest_discovery.json"
            (archive / "figures").mkdir(parents=True)
            registry.parent.mkdir(parents=True)
            (archive / "figures" / "chart.png").write_bytes(b"chart")
            snapshot = archive / "market_data" / "snapshots.jsonl"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                json.dumps({"timestamp": "before", "families": [{"name": "Saved"}]}) + "\n",
                encoding="utf-8",
            )
            registry.write_text("{}", encoding="utf-8")
            discovery.write_text("{}", encoding="utf-8")
            state = DashboardState()
            state.pending_events = [{"event_id": "event-1"}]
            with (
                patch("antilego.dashboard.weekly_archive_dir", return_value=archive),
                patch("antilego.dashboard.live_snapshot_path", return_value=snapshot),
                patch("antilego.dashboard.DEFAULT_MONITORING_REGISTRY", registry),
                patch("antilego.dashboard.MONITORING_DIR", discovery.parent),
            ):
                state.clear_all_data()
            self.assertTrue((archive / "figures" / "chart.png").exists())
            self.assertEqual(json.loads(registry.read_text(encoding="utf-8"))["families"], [])
            self.assertEqual(json.loads(discovery.read_text(encoding="utf-8"))["events"], [])
            self.assertIn('"event":"dashboard_reset"', snapshot.read_text(encoding="utf-8"))
            self.assertEqual(_snapshot_history(snapshot)["families"], [])
            self.assertEqual(state.pending_events, [])

    def test_history_preserves_violation_windows_and_magnitude(self):
        records = [
            {
                "timestamp": "2026-10-11T10:00:00+00:00",
                "families": [{"name": "Example", "type": "complements", "coherent": True, "violations": []}],
            },
            {
                "timestamp": "2026-10-11T10:02:00+00:00",
                "families": [{"name": "Example", "type": "complements", "coherent": False, "violations": [{"magnitude": 0.04}]}],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            history = _snapshot_history(path)
        points = history["families"][0]["points"]
        self.assertFalse(points[0]["violating"])
        self.assertTrue(points[1]["violating"])
        self.assertEqual(points[1]["magnitude"], 0.04)
        self.assertEqual(points[1]["value"], 0.04)

    def test_sum_history_uses_percentage_value_and_one_hundred_percent_ideal(self):
        record = {
            "timestamp": "2026-10-11T10:00:00+00:00",
            "families": [{
                "name": "League winner",
                "type": "exhaustive_outcomes",
                "coherent": True,
                "sum": 1.02,
                "violations": [],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            family = _snapshot_history(path)["families"][0]
        self.assertEqual(family["ideal_value"], 1.0)
        self.assertEqual(family["points"][0]["value"], 1.02)
        self.assertEqual(family["metric_label"], "executable basket totals")
        self.assertEqual(family["chart_mode"], "basket_totals")

    def test_exhaustive_history_keeps_buy_and_sell_basket_totals(self):
        record = {
            "timestamp": "2026-10-11T10:00:00+00:00",
            "families": [{
                "name": "League winner",
                "type": "exhaustive_outcomes",
                "coherent": True,
                "sum": 1.01,
                "violations": [],
                "markets": [
                    {"label": "A", "buy_price": 0.55, "sell_price": 0.52},
                    {"label": "B", "buy_price": 0.46, "sell_price": 0.43},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            family = _snapshot_history(path)["families"][0]
        self.assertEqual(
            [series["label"] for series in family["market_series"]],
            ["Buy all outcomes", "Sell all outcomes"],
        )
        self.assertAlmostEqual(family["market_series"][0]["points"][0]["value"], 1.01)
        self.assertAlmostEqual(family["market_series"][1]["points"][0]["value"], 0.95)
        self.assertEqual((family["lower_bound"], family["upper_bound"]), (0.97, 1.03))

    def test_ordered_law_history_exposes_each_contract_probability(self):
        record = {
            "timestamp": "2026-10-13T10:00:00+00:00",
            "families": [{
                "name": "Ceasefire continues",
                "type": "survival_deadline_nesting",
                "coherent": True,
                "violations": [],
                "markets": [
                    {"label": "October", "buy_price": 0.72, "sell_price": 0.68},
                    {"label": "November", "buy_price": 0.62, "sell_price": 0.58},
                ],
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            path.write_text(json.dumps(record), encoding="utf-8")
            family = _snapshot_history(path)["families"][0]
        self.assertEqual(family["chart_mode"], "market_probabilities")
        self.assertEqual(family["metric_label"], "executable probability by contract")
        self.assertEqual(
            [series["label"] for series in family["market_series"]],
            ["October", "November"],
        )
        self.assertAlmostEqual(family["market_series"][0]["points"][0]["value"], 0.70)
        self.assertAlmostEqual(family["market_series"][0]["points"][0]["buy_value"], 0.72)
        self.assertAlmostEqual(family["market_series"][0]["points"][0]["sell_value"], 0.68)

    def test_ordered_history_keeps_quote_gaps_visible(self):
        records = [
            {
                "timestamp": "2026-10-13T10:00:00+00:00",
                "families": [{
                    "name": "Deadline chain",
                    "type": "deadline_nesting",
                    "coherent": True,
                    "violations": [],
                    "markets": [
                        {"label": "October", "buy_price": 0.40, "sell_price": 0.36},
                        {"label": "November", "buy_price": 0.60, "sell_price": 0.56},
                    ],
                }],
            },
            {
                "timestamp": "2026-10-13T10:03:00+00:00",
                "families": [{
                    "name": "Deadline chain",
                    "type": "deadline_nesting",
                    "coherent": None,
                    "data_complete": False,
                    "violations": [],
                    "markets": [
                        {"label": "October", "buy_price": None, "sell_price": None},
                        {"label": "November", "buy_price": 0.61, "sell_price": 0.57},
                    ],
                }],
            },
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshots.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            family = _snapshot_history(path)["families"][0]
        self.assertIsNone(family["market_series"][0]["points"][1]["value"])
        self.assertAlmostEqual(family["market_series"][1]["points"][1]["value"], 0.59)

    @patch("antilego.dashboard.subprocess.Popen")
    def test_notification_only_fires_when_family_enters_violation(self, popen):
        state = DashboardState()
        violating = {
            "timestamp": "2026-10-11T10:00:00+00:00",
            "families": [{"name": "Example", "coherent": False, "violation_count": 1}],
        }
        state._record_violation_notifications(violating)
        state._record_violation_notifications(violating)
        state._record_violation_notifications({"timestamp": "later", "families": [{"name": "Example", "coherent": True}]})
        state._record_violation_notifications(violating)
        self.assertEqual(len(state.notifications), 2)
        self.assertEqual(popen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
