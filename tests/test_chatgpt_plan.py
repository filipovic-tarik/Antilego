import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from antilego import chatgpt_plan
from antilego.chatgpt_plan import (
    ChatGPTPlanSession,
    _parse_sse_response,
    _select_model,
)


class ChatGPTPlanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.patches = [
            patch.object(chatgpt_plan, "APP_SUPPORT_DIR", root),
            patch.object(chatgpt_plan, "HOST_PATH", root / "host.json"),
            patch.object(chatgpt_plan, "PROFILE_PATH", root / "profile.json"),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temporary.cleanup()

    def test_authorization_uses_pkce_and_required_plan_scope(self):
        session = ChatGPTPlanSession()
        authorization_url = session.begin_authorization(
            "http://127.0.0.1:8766/auth/callback"
        )
        query = parse_qs(urlparse(authorization_url).query)

        self.assertEqual(query["client_id"], ["dynamic_agent_client"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertIn("chatgpt.tokens.use.direct", query["scope"][0].split())
        self.assertEqual(query["state"], [session.pending.state])
        self.assertTrue(query["ext_agent_host_id"][0].startswith("urn:uuid:"))

    def test_sse_parser_collects_structured_output(self):
        complete = {
            "type": "response.completed",
            "response": {"id": "resp_1", "output": []},
        }
        stream = io.BytesIO(
            b'data: {"type":"response.output_text.delta","delta":"{\\"ok\\":"}\n\n'
            b'data: {"type":"response.output_text.delta","delta":"true}"}\n\n'
            + f"data: {json.dumps(complete)}\n\n".encode()
            + b"data: [DONE]\n\n"
        )

        result = _parse_sse_response(stream)

        self.assertEqual(result["id"], "resp_1")
        self.assertEqual(result["output_text"], '{"ok":true}')

    def test_account_catalog_prefers_supported_sol_model(self):
        selected = _select_model(
            [
                {"slug": "another-model", "display_name": "Another"},
                {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol"},
            ]
        )
        self.assertEqual(selected["slug"], "gpt-6.1-sol")

    def test_connected_profile_is_private_and_disconnect_removes_it(self):
        chatgpt_plan._atomic_private_json(
            chatgpt_plan.PROFILE_PATH,
            {
                "email": "tarik@example.com",
                "client_id": "client",
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": time.time() + 3600,
                "scopes": ["chatgpt.tokens.use.direct"],
            },
        )
        session = ChatGPTPlanSession()

        self.assertTrue(session.connected)
        self.assertEqual(session.status()["email"], "tarik@example.com")
        self.assertEqual(chatgpt_plan.PROFILE_PATH.stat().st_mode & 0o777, 0o600)

        session.disconnect()
        self.assertFalse(session.connected)
        self.assertFalse(chatgpt_plan.PROFILE_PATH.exists())

    def test_plan_transport_uses_account_model_and_required_privacy_flags(self):
        chatgpt_plan._atomic_private_json(
            chatgpt_plan.PROFILE_PATH,
            {
                "email": "tarik@example.com",
                "client_id": "client",
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_at": time.time() + 3600,
                "scopes": ["chatgpt.tokens.use.direct"],
                "model": "gpt-6.1-sol",
                "model_display_name": "GPT-6.1 Sol",
            },
        )
        captured = {}

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(request, timeout):
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            complete = {
                "type": "response.completed",
                "response": {"id": "resp_1", "output": []},
            }
            return FakeResponse(
                b'data: {"type":"response.output_text.delta","delta":"{}"}\n\n'
                + f"data: {json.dumps(complete)}\n\n".encode()
            )

        session = ChatGPTPlanSession()
        with patch.object(chatgpt_plan.urllib.request, "urlopen", fake_urlopen):
            result = session.response_transport(
                {"model": "wrong-model", "input": "classify this"},
                "unused",
            )

        self.assertEqual(result["output_text"], "{}")
        self.assertEqual(captured["payload"]["model"], "gpt-6.1-sol")
        self.assertFalse(captured["payload"]["store"])
        self.assertTrue(captured["payload"]["stream"])


if __name__ == "__main__":
    unittest.main()
