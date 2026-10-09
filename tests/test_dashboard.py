import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from antilego.dashboard import DashboardServer


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


if __name__ == "__main__":
    unittest.main()
