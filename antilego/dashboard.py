"""Private localhost dashboard for controlling the Antilego engine."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import secrets
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .chatgpt_plan import ChatGPTPlanSession
from .market_discovery import discovery_report, write_discovery_report
from .market_tracking import append_snapshot, collect_snapshot
from .monitoring_registry import load_monitored_families, register_classified_events
from .paths import (
    DEFAULT_MONITORING_REGISTRY,
    MONITORING_DIR,
    PROJECT_ROOT,
    live_snapshot_path,
    weekly_archive_dir,
    weekly_figures_dir,
)
from .relationship_intelligence import classify_relationship

STATIC_DIR = Path(__file__).resolve().parent / "dashboard_static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766


def _latest_jsonl_record(path: Path) -> dict | None:
    if not path.exists():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not lines:
        return None
    try:
        payload = json.loads(lines[-1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class DashboardState:
    """Thread-safe orchestration state shared by the local HTTP handlers."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.chatgpt = ChatGPTPlanSession()
        self.monitor_stop = threading.Event()
        self.monitor_thread: threading.Thread | None = None
        self.discovery_thread: threading.Thread | None = None
        self.graph_thread: threading.Thread | None = None
        self.monitor_state = "stopped"
        self.monitor_message = "Ready to monitor approved families."
        self.monitor_interval_minutes = 5.0
        self.next_snapshot_at: str | None = None
        self.discovery = {
            "state": "idle",
            "message": "No discovery has been run in this session.",
            "processed": 0,
            "total": 0,
        }
        self.graphs = {
            "state": "idle",
            "message": "Generate graphs after collecting complete snapshots.",
        }

    def begin_chatgpt_connection(self, redirect_uri: str) -> str:
        with self.lock:
            return self.chatgpt.begin_authorization(redirect_uri)

    def complete_chatgpt_connection(self, query: dict[str, list[str]]) -> None:
        try:
            with self.lock:
                self.chatgpt.complete_authorization(query)
        except Exception as error:
            with self.lock:
                self.chatgpt.last_error = str(error)
            raise

    def disconnect_chatgpt(self) -> None:
        with self.lock:
            if self.discovery_thread and self.discovery_thread.is_alive():
                raise ValueError("Wait for market discovery to finish before disconnecting.")
            self.chatgpt.disconnect()

    def start_discovery(self, limit: int, minimum_confidence: float) -> None:
        if not 1 <= limit <= 50:
            raise ValueError("Discovery limit must be between 1 and 50.")
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("Minimum confidence must be between 0 and 1.")
        with self.lock:
            if not self.chatgpt.connected:
                raise ValueError("Connect your ChatGPT plan before discovering markets.")
            if self.discovery_thread and self.discovery_thread.is_alive():
                raise ValueError("Market discovery is already running.")
            self.discovery = {
                "state": "running",
                "message": "Finding active Polymarket event groups for plan-backed review...",
                "processed": 0,
                "total": 0,
            }
            self.discovery_thread = threading.Thread(
                target=self._run_discovery,
                args=(limit, minimum_confidence),
                daemon=True,
                name="antilego-discovery",
            )
            self.discovery_thread.start()

    def _run_discovery(
        self,
        limit: int,
        minimum_confidence: float,
    ) -> None:
        try:
            report = discovery_report(limit=limit)
            events = report["events"]
            with self.lock:
                self.discovery.update(
                    total=len(events),
                    message=f"Classifying {len(events)} active event group(s)...",
            )
            for index, event in enumerate(events, start=1):
                result = classify_relationship(
                    event["contracts"],
                    api_key="chatgpt-plan",
                    transport=self.chatgpt.response_transport,
                )
                event["classification"] = result.to_dict()
                with self.lock:
                    self.discovery.update(
                        processed=index,
                        message=f"Classified {index} of {len(events)} event group(s).",
                    )
            summary = register_classified_events(
                events,
                registry_path=DEFAULT_MONITORING_REGISTRY,
                minimum_confidence=minimum_confidence,
            )
            report["monitoring"] = summary
            write_discovery_report(report, MONITORING_DIR / "latest_discovery.json")
            accepted = len(summary["accepted"])
            skipped = len(summary["skipped"])
            with self.lock:
                self.discovery.update(
                    state="complete",
                    message=(
                        f"Discovery complete: {accepted} group(s) approved for "
                        f"monitoring and {skipped} skipped."
                    ),
                )
        except Exception as error:  # Surface background failures in the UI.
            with self.lock:
                self.discovery.update(state="error", message=str(error))

    def start_monitoring(self, interval_minutes: float = 5) -> None:
        if interval_minutes <= 0:
            raise ValueError("Monitoring interval must be greater than zero.")
        families = load_monitored_families()
        if not families:
            raise ValueError("Discover and approve at least one market group first.")
        with self.lock:
            if self.monitor_thread and self.monitor_thread.is_alive():
                raise ValueError("Monitoring is already running.")
            self.monitor_interval_minutes = interval_minutes
            self.monitor_stop.clear()
            self.monitor_state = "running"
            self.monitor_message = "Collecting the first price snapshot..."
            self.next_snapshot_at = None
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="antilego-monitor",
            )
            self.monitor_thread.start()

    def _monitor_loop(self) -> None:
        try:
            while not self.monitor_stop.is_set():
                families = load_monitored_families()
                if not families:
                    raise RuntimeError("The monitoring registry is empty.")
                snapshot = collect_snapshot(families)
                output_path = append_snapshot(snapshot)
                next_time = datetime.now(timezone.utc) + timedelta(
                    minutes=self.monitor_interval_minutes
                )
                violations = sum(
                    family.get("violation_count", 0)
                    for family in snapshot.get("families", [])
                )
                with self.lock:
                    self.monitor_message = (
                        f"Saved {len(snapshot['families'])} family result(s) to "
                        f"{output_path.name}; {violations} violation(s) detected."
                    )
                    self.next_snapshot_at = next_time.isoformat()
                if self.monitor_stop.wait(self.monitor_interval_minutes * 60):
                    break
        except Exception as error:  # Surface background failures in the UI.
            with self.lock:
                self.monitor_state = "error"
                self.monitor_message = str(error)
                self.next_snapshot_at = None
        finally:
            with self.lock:
                if self.monitor_state != "error":
                    self.monitor_state = "stopped"
                    self.monitor_message = "Monitoring stopped."
                self.next_snapshot_at = None

    def stop_monitoring(self) -> None:
        with self.lock:
            if not self.monitor_thread or not self.monitor_thread.is_alive():
                self.monitor_state = "stopped"
                self.monitor_message = "Monitoring is already stopped."
                return
            self.monitor_message = "Stopping after the current price request..."
            self.monitor_stop.set()

    def generate_graphs(self) -> None:
        with self.lock:
            if self.graph_thread and self.graph_thread.is_alive():
                raise ValueError("Graph generation is already running.")
            if not live_snapshot_path().exists():
                raise ValueError("Collect at least one snapshot before generating graphs.")
            self.graphs = {"state": "running", "message": "Generating current graphs..."}
            self.graph_thread = threading.Thread(
                target=self._run_graphs,
                daemon=True,
                name="antilego-graphs",
            )
            self.graph_thread.start()

    def _run_graphs(self) -> None:
        command = [
            sys.executable,
            str(PROJECT_ROOT / "antilego" / "analysis" / "antilego_analysis.py"),
            "--no-show",
        ]
        try:
            result = subprocess.run(
                command,
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=240,
                check=False,
            )
            if result.returncode:
                detail = (result.stderr or result.stdout).strip().splitlines()
                raise RuntimeError(detail[-1] if detail else "Graph generation failed.")
            with self.lock:
                self.graphs = {
                    "state": "complete",
                    "message": "Graphs updated from the current weekly snapshots.",
                }
        except Exception as error:
            with self.lock:
                self.graphs = {"state": "error", "message": str(error)}

    def open_data_folder(self) -> None:
        destination = weekly_archive_dir()
        destination.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["/usr/bin/open", str(destination)])

    def status(self) -> dict:
        families = load_monitored_families()
        snapshot = _latest_jsonl_record(live_snapshot_path())
        latest_by_name = {
            family.get("name"): family
            for family in (snapshot or {}).get("families", [])
            if isinstance(family, dict)
        }
        monitored = []
        for family in families:
            latest = latest_by_name.get(family.get("name"), {})
            monitored.append(
                {
                    "name": family.get("name"),
                    "type": family.get("type"),
                    "market_count": len(family.get("markets", [])),
                    "confidence": family.get("source", {}).get(
                        "classification_confidence"
                    ),
                    "coherent": latest.get("coherent"),
                    "data_complete": latest.get("data_complete"),
                    "violation_count": latest.get("violation_count", 0),
                    "missing_prices": latest.get("missing_prices", 0),
                    "violations": latest.get("violations", []),
                }
            )
        figures = []
        for path in sorted(weekly_figures_dir().glob("*.png")):
            figures.append(
                {
                    "name": path.name,
                    "url": f"/figures/{path.name}?v={path.stat().st_mtime_ns}",
                }
            )
        with self.lock:
            return {
                "chatgpt": self.chatgpt.status(),
                "monitor": {
                    "state": self.monitor_state,
                    "message": self.monitor_message,
                    "interval_minutes": self.monitor_interval_minutes,
                    "next_snapshot_at": self.next_snapshot_at,
                },
                "discovery": dict(self.discovery),
                "graphs": {**self.graphs, "items": figures},
                "monitored_families": monitored,
                "family_count": len(monitored),
                "latest_snapshot_at": (snapshot or {}).get("timestamp"),
                "latest_violation_count": sum(
                    family.get("violation_count", 0)
                    for family in (snapshot or {}).get("families", [])
                ),
                "snapshot_path": str(live_snapshot_path()),
                "archive_path": str(weekly_archive_dir()),
            }


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], state: DashboardState):
        super().__init__(address, DashboardHandler)
        self.state = state
        self.csrf_token = secrets.token_urlsafe(24)
        self.base_url = f"http://{self.server_address[0]}:{self.server_address[1]}"


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, title: str, message: str, *, success: bool) -> None:
        color = "#42dc8f" if success else "#ed6a6a"
        body = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<body style="margin:0;background:#07100d;color:#edf5f0;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">
<main style="max-width:680px;margin:14vh auto;padding:32px;border:1px solid rgba(214,238,225,.18)">
<p style="color:{color};letter-spacing:.16em;text-transform:uppercase">Antilego / ChatGPT</p>
<h1 style="font-size:clamp(2.5rem,7vw,5rem);line-height:.92">{html.escape(title)}</h1>
<p style="color:#93a49b;font-size:1.05rem;line-height:1.7">{html.escape(message)}</p>
<a href="/" style="display:inline-block;margin-top:24px;padding:14px 18px;color:#07100d;background:{color};text-decoration:none;font-weight:700">Return to Antilego</a>
</main></body></html>""".encode("utf-8")
        self.send_response(200 if success else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid request length.") from error
        if length <= 0 or length > 16_384:
            raise ValueError("Invalid request body.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Request body must be valid JSON.") from error
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _post_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            if parsed.hostname not in {"127.0.0.1", "localhost"}:
                return False
        return secrets.compare_digest(
            self.headers.get("X-Antilego-Token", ""),
            self.server.csrf_token,
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/auth/callback":
            from urllib.parse import parse_qs

            try:
                self.server.state.complete_chatgpt_connection(parse_qs(parsed.query))
                self._send_html(
                    "ChatGPT connected",
                    "Your plan can now power Antilego's market-relationship analysis. The credential is protected locally on this Mac.",
                    success=True,
                )
            except Exception as error:
                self._send_html("Connection failed", str(error), success=False)
            return
        if parsed.path == "/api/status":
            payload = self.server.state.status()
            payload["csrf_token"] = self.server.csrf_token
            self._send_json(payload)
            return
        if parsed.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html")
            return
        if parsed.path.startswith("/static/"):
            name = Path(parsed.path).name
            if name not in {"app.css", "app.js"}:
                self.send_error(404)
                return
            self._send_file(STATIC_DIR / name)
            return
        if parsed.path == "/logo.png":
            self._send_file(PROJECT_ROOT / "assets" / "antilego_logo_only.png")
            return
        if parsed.path.startswith("/figures/"):
            name = Path(parsed.path).name
            if name != parsed.path.removeprefix("/figures/") or not name.endswith(".png"):
                self.send_error(404)
                return
            self._send_file(weekly_figures_dir() / name)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if not self._post_allowed():
            self._send_json({"error": "Request rejected."}, 403)
            return
        try:
            payload = self._read_json()
            path = urlparse(self.path).path
            if path == "/api/chatgpt/connect":
                authorization_url = self.server.state.begin_chatgpt_connection(
                    f"{self.server.base_url}/auth/callback"
                )
                self._send_json({"ok": True, "authorization_url": authorization_url})
                return
            elif path == "/api/chatgpt/disconnect":
                self.server.state.disconnect_chatgpt()
            elif path == "/api/discover":
                self.server.state.start_discovery(
                    int(payload.get("limit", 10)),
                    float(payload.get("minimum_confidence", 0.8)),
                )
            elif path == "/api/monitor/start":
                self.server.state.start_monitoring(
                    float(payload.get("interval_minutes", 5))
                )
            elif path == "/api/monitor/stop":
                self.server.state.stop_monitoring()
            elif path == "/api/graphs":
                self.server.state.generate_graphs()
            elif path == "/api/open-folder":
                self.server.state.open_data_folder()
            elif path == "/api/quit":
                self.server.state.stop_monitoring()
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send_json({"error": "Unknown action."}, 404)
                return
            self._send_json({"ok": True, "status": self.server.state.status()})
        except (TypeError, ValueError) as error:
            self._send_json({"error": str(error)}, 400)
        except Exception as error:
            self._send_json({"error": str(error)}, 500)


def run_dashboard(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
) -> None:
    state = DashboardState()
    url = f"http://{host}:{port}"
    try:
        server = DashboardServer((host, port), state)
    except OSError:
        if open_browser:
            webbrowser.open(url)
            return
        raise
    if open_browser:
        threading.Timer(0.35, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.25)
    finally:
        state.stop_monitoring()
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the private Antilego dashboard")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    run_dashboard(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
