"""Local Sign in with ChatGPT support for plan-backed Antilego inference."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import jwt
from jwt import PyJWKClient

AUTHORIZATION_URL = "https://auth.openai.com/api/accounts/authorize"
TOKEN_URL = "https://auth.openai.com/api/accounts/oauth/token"
JWKS_URL = "https://auth.openai.com/.well-known/jwks.json"
RESPONSES_URL = "https://api.openai.com/v1/responses"
MODELS_URL = "https://api.openai.com/v1/models"
ISSUER = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
APP_NAME = "Antilego"
APP_ID = "antilego"
PREFERRED_MODELS = ("gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol")

APP_SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "Antilego"
HOST_PATH = APP_SUPPORT_DIR / "chatgpt-host.json"
PROFILE_PATH = APP_SUPPORT_DIR / "chatgpt-profile.json"


def _atomic_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, stat.S_IRWXU)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.chmod(temporary, stat.S_IRUSR | stat.S_IWUSR)
    temporary.replace(path)


def _read_private_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _host_id() -> str:
    existing = _read_private_json(HOST_PATH)
    if existing and isinstance(existing.get("ext_agent_host_id"), str):
        return existing["ext_agent_host_id"]
    value = f"urn:uuid:{uuid.uuid4()}"
    _atomic_private_json(HOST_PATH, {"ext_agent_host_id": value})
    return value


def _post_form(url: str, fields: dict[str, str]) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Antilego/2.0 (local research application)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ChatGPT authorization failed ({error.code}): {detail}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"ChatGPT authorization failed: {error}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("ChatGPT authorization returned an unexpected response.")
    return payload


def _available_models(access_token: str) -> list[dict[str, str]]:
    request = urllib.request.Request(
        MODELS_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "Antilego/2.0 (local research application)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"ChatGPT model catalog failed ({error.code}): {detail}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"ChatGPT model catalog failed: {error}") from error
    models = payload.get("models", []) if isinstance(payload, dict) else []
    visible = []
    for model in models:
        if not isinstance(model, dict) or model.get("visibility") != "list":
            continue
        slug = model.get("slug")
        if isinstance(slug, str) and slug:
            visible.append(
                {
                    "slug": slug,
                    "display_name": str(model.get("display_name") or slug),
                }
            )
    if not visible:
        raise RuntimeError("Your ChatGPT account did not return an eligible model.")
    return visible


def _select_model(models: list[dict[str, str]]) -> dict[str, str]:
    by_slug = {model["slug"]: model for model in models}
    for slug in PREFERRED_MODELS:
        if slug in by_slug:
            return by_slug[slug]
    return models[0]


def _validate_id_token(token: str, client_id: str, nonce: str) -> dict:
    signing_key = PyJWKClient(JWKS_URL).get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=client_id,
        issuer=ISSUER,
    )
    if not secrets.compare_digest(str(claims.get("nonce", "")), nonce):
        raise RuntimeError("ChatGPT authorization nonce did not match.")
    return claims


def _parse_sse_response(response) -> dict:
    output_parts: list[str] = []
    completed: dict | None = None
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        event_type = event.get("type")
        if event_type == "response.output_text.delta":
            output_parts.append(str(event.get("delta", "")))
        elif event_type == "response.completed":
            completed = event.get("response") if isinstance(event.get("response"), dict) else event
        elif event_type in {"response.failed", "response.incomplete"}:
            response_payload = event.get("response", {})
            error = response_payload.get("error") if isinstance(response_payload, dict) else None
            if isinstance(error, dict):
                detail = error.get("message") or error.get("code") or "unknown error"
            else:
                detail = "the response did not complete"
            raise RuntimeError(f"ChatGPT plan request failed: {detail}")
    if completed is None:
        raise RuntimeError("ChatGPT plan stream ended before completion.")
    output_text = "".join(output_parts)
    if not output_text:
        for item in completed.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    output_text += str(content.get("text", ""))
    return {**completed, "output_text": output_text}


@dataclass
class PendingAuthorization:
    state: str
    nonce: str
    verifier: str
    redirect_uri: str
    client_id: str


class ChatGPTPlanSession:
    """Own OAuth state and perform eligible Responses calls for this Mac."""

    def __init__(self) -> None:
        self.profile = _read_private_json(PROFILE_PATH)
        self.pending: PendingAuthorization | None = None
        self.last_error: str | None = None

    @property
    def connected(self) -> bool:
        return bool(
            self.profile
            and "chatgpt.tokens.use.direct" in self.profile.get("scopes", [])
            and self.profile.get("refresh_token")
        )

    def begin_authorization(self, redirect_uri: str) -> str:
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        saved_client_id = (
            str(self.profile.get("client_id"))
            if self.profile and self.profile.get("client_id")
            else "dynamic_agent_client"
        )
        self.pending = PendingAuthorization(
            state=state,
            nonce=nonce,
            verifier=verifier,
            redirect_uri=redirect_uri,
            client_id=saved_client_id,
        )
        params = {
            "client_id": saved_client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "ext_agent_host_id": _host_id(),
        }
        if saved_client_id == "dynamic_agent_client":
            params["agent_name_hint"] = APP_NAME
        elif self.profile:
            if self.profile.get("id_token"):
                params["id_token_hint"] = str(self.profile["id_token"])
            elif self.profile.get("email"):
                params["login_hint"] = str(self.profile["email"])
        self.last_error = None
        return f"{AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"

    def complete_authorization(self, query: dict[str, list[str]]) -> None:
        pending = self.pending
        if not pending:
            raise RuntimeError("No ChatGPT authorization is currently pending.")
        returned_state = (query.get("state") or [""])[0]
        if not secrets.compare_digest(returned_state, pending.state):
            raise RuntimeError("ChatGPT authorization state did not match.")
        if query.get("error"):
            detail = (query.get("error_description") or query["error"])[0]
            raise RuntimeError(f"ChatGPT authorization was not completed: {detail}")
        code = (query.get("code") or [""])[0]
        callback_client_id = (query.get("client_id") or [""])[0]
        if pending.client_id == "dynamic_agent_client":
            if not callback_client_id or callback_client_id == "dynamic_agent_client":
                raise RuntimeError("ChatGPT did not issue an application client ID.")
            client_id = callback_client_id
        else:
            client_id = pending.client_id
            if callback_client_id and callback_client_id != client_id:
                raise RuntimeError("ChatGPT returned a different application client ID.")
        if not code:
            raise RuntimeError("ChatGPT authorization did not return a code.")
        token_payload = _post_form(
            TOKEN_URL,
            {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": pending.verifier,
                "redirect_uri": pending.redirect_uri,
                "resource": RESOURCE,
            },
        )
        id_token = str(token_payload.get("id_token", ""))
        claims = _validate_id_token(id_token, client_id, pending.nonce)
        scopes = str(token_payload.get("scope", "")).split()
        if "chatgpt.tokens.use.direct" not in scopes:
            raise RuntimeError("ChatGPT plan usage was not authorized.")
        now = time.time()
        profile = {
            "email": claims.get("email"),
            "issuer": claims.get("iss"),
            "subject": claims.get("sub"),
            "client_id": client_id,
            "ext_agent_host_id": _host_id(),
            "id_token": id_token,
            "access_token": token_payload.get("access_token"),
            "refresh_token": token_payload.get("refresh_token"),
            "token_type": token_payload.get("token_type", "Bearer"),
            "expires_at": now + int(token_payload.get("expires_in", 3600)),
            "scopes": scopes,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        if not profile["access_token"] or not profile["refresh_token"]:
            raise RuntimeError("ChatGPT authorization did not return reusable credentials.")
        models = _available_models(str(profile["access_token"]))
        selected_model = _select_model(models)
        profile["models"] = models
        profile["model"] = selected_model["slug"]
        profile["model_display_name"] = selected_model["display_name"]
        _atomic_private_json(PROFILE_PATH, profile)
        self.profile = profile
        self.pending = None
        self.last_error = None

    def disconnect(self) -> None:
        self.profile = None
        self.pending = None
        self.last_error = None
        try:
            PROFILE_PATH.unlink()
        except FileNotFoundError:
            pass

    def _refresh_if_needed(self) -> None:
        if not self.connected or not self.profile:
            raise RuntimeError("Connect your ChatGPT plan before discovering markets.")
        if float(self.profile.get("expires_at", 0)) > time.time() + 90:
            return
        payload = _post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "client_id": str(self.profile["client_id"]),
                "refresh_token": str(self.profile["refresh_token"]),
                "resource": RESOURCE,
            },
        )
        self.profile.update(
            access_token=payload.get("access_token"),
            refresh_token=payload.get("refresh_token", self.profile["refresh_token"]),
            token_type=payload.get("token_type", "Bearer"),
            expires_at=time.time() + int(payload.get("expires_in", 3600)),
            scopes=str(payload.get("scope", " ".join(self.profile["scopes"]))).split(),
            saved_at=datetime.now(timezone.utc).isoformat(),
        )
        if not self.profile.get("access_token"):
            raise RuntimeError("ChatGPT token refresh did not return an access token.")
        _atomic_private_json(PROFILE_PATH, self.profile)

    def status(self) -> dict:
        return {
            "connected": self.connected,
            "email": self.profile.get("email") if self.connected and self.profile else None,
            "model": self.profile.get("model") if self.connected and self.profile else None,
            "model_display_name": (
                self.profile.get("model_display_name")
                if self.connected and self.profile
                else None
            ),
            "message": (
                "ChatGPT plan connected."
                if self.connected
                else self.last_error or "Connect ChatGPT to enable plan-backed discovery."
            ),
        }

    def response_transport(self, request_payload: dict, _credential: str) -> dict:
        self._refresh_if_needed()
        assert self.profile is not None
        payload = {
            **request_payload,
            "model": self.profile.get("model") or request_payload.get("model"),
            "input": [
                {
                    "role": "user",
                    "content": str(request_payload.get("input", "")),
                }
            ],
            "store": False,
            "stream": True,
        }
        request = urllib.request.Request(
            RESPONSES_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.profile['access_token']}",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "User-Agent": "Antilego/2.0 (local research application)",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return _parse_sse_response(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ChatGPT plan request failed ({error.code}): {detail}"
            ) from error
        except OSError as error:
            raise RuntimeError(f"ChatGPT plan request failed: {error}") from error


SessionFactory = Callable[[], ChatGPTPlanSession]
