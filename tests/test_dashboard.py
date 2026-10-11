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
    def test_default_snapshot_interval_is_two_minutes(self):
        self.assertEqual(DEFAULT_SNAPSHOT_INTERVAL_MINUTES, 2.0)

    def test_empty_selection_does_not_approve_everything(self):
        state = DashboardState()
        state.pending_events = [{"event_id": "event-1", "approval_eligible": True}]
        with self.assertRaisesRegex(ValueError, "Select at least one"):
            state.approve_discovery([])

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
