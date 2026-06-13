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
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlparse

from .chatgpt_plan import ChatGPTPlanSession
from .contradiction_brain import PROBABILITY_LAWS
from .market_discovery import discovery_report, write_discovery_report
from .market_tracking import append_snapshot, collect_snapshot
from .monitoring_registry import (
    family_from_classification,
    load_monitored_families,
    register_classified_events,
    write_monitored_families,
)
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
DEFAULT_SNAPSHOT_INTERVAL_MINUTES = 3.0
AI_DISCOVERY_INTERVAL_HOURS = 1
HISTORY_LIMIT = 360
ORDERED_PROBABILITY_LAWS = {
    "deadline_nesting",
    "survival_deadline_nesting",
    "threshold_chain",
    "logical_implication",
}
EXACT_SUM_LAWS = {"exhaustive_outcomes", "mutually_exclusive", "complements"}


def _polymarket_event_url(family: dict) -> str | None:
    event_slug = str(family.get("source", {}).get("event_slug") or "").strip()
    if not event_slug:
        return None
    return f"https://polymarket.com/event/{quote(event_slug, safe='')}"


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


def _snapshot_history(path: Path, limit: int = HISTORY_LIMIT) -> dict:
    """Return compact chart data from recent snapshots."""
    if not path.exists():
        return {"snapshot_count": 0, "families": []}
    records = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    last_reset = max(
        (index for index, record in enumerate(records) if record.get("event") == "dashboard_reset"),
        default=-1,
    )
    records = records[last_reset + 1 :]
    series: dict[str, dict] = {}
    for record in records:
        timestamp = record.get("timestamp")
        for family in record.get("families", []):
            if not isinstance(family, dict) or not family.get("name"):
                continue
            violations = family.get("violations") or []
            magnitude = max(
                (
                    float(item.get("magnitude", 0))
                    for item in violations
                    if isinstance(item, dict)
                ),
                default=0.0,
            )
            total = family.get("sum")
            uses_probability_sum = isinstance(total, (int, float))
            uses_market_probabilities = family.get("type") in ORDERED_PROBABILITY_LAWS
            uses_basket_totals = family.get("type") in EXACT_SUM_LAWS
            value = float(total) if uses_probability_sum else magnitude
            ideal_value = 1.0 if uses_probability_sum else 0.0
            ideal_label = (
                "100% line of perfect consistency"
                if family.get("type") in {
                    "exhaustive_outcomes",
                    "mutually_exclusive",
                    "complements",
                }
                else "100% consistency boundary"
                if uses_probability_sum
                else "probabilities ordered earlier to later"
                if family.get("type") == "deadline_nesting"
                else "probabilities ordered from higher to lower"
                if family.get("type") in {
                    "survival_deadline_nesting",
                    "threshold_chain",
                }
                else "0% line of perfect consistency"
            )
            item = series.setdefault(
                family["name"],
                {
                    "name": family["name"],
                    "law": family.get("type"),
                    "metric_label": (
                        "executable basket totals"
                        if uses_basket_totals
                        else "combined probability"
                        if uses_probability_sum
                        else "executable probability by contract"
                        if uses_market_probabilities
                        else "probability discrepancy"
                    ),
                    "chart_mode": (
                        "market_probabilities"
                        if uses_market_probabilities
                        else "basket_totals"
                        if uses_basket_totals
                        else "consistency"
                    ),
                    "ideal_value": ideal_value,
                    "ideal_label": ideal_label,
                    "points": [],
                    "market_series": [],
                    "lower_bound": (
                        0.97
                        if family.get("type") in {"exhaustive_outcomes", "mutually_exclusive"}
                        else 0.995
                        if family.get("type") == "complements"
                        else None
                    ),
                    "upper_bound": (
                        1.03
                        if family.get("type") in {"exhaustive_outcomes", "mutually_exclusive"}
                        else 1.005
                        if family.get("type") == "complements"
                        else None
                    ),
                    "latest_violations": [],
                    "target_shares": family.get("target_shares"),
                },
            )
            item["points"].append(
                {
                    "timestamp": timestamp,
                    "value": value,
                    "magnitude": magnitude,
                    "violating": family.get("coherent") is False,
                    "complete": family.get("data_complete") is not False,
                }
            )
            point_index = len(item["points"]) - 1
            item["latest_violations"] = [
                {
                    "left": violation.get("left"),
                    "right": violation.get("right"),
                    "magnitude": float(violation.get("magnitude", 0)),
                }
                for violation in violations
                if isinstance(violation, dict)
            ]
            item["target_shares"] = family.get("target_shares") or item.get("target_shares")
            if uses_market_probabilities:
                for existing_series in item["market_series"]:
                    existing_series["points"].append(
                        {
                            "index": point_index,
                            "timestamp": timestamp,
                            "value": None,
                            "buy_value": None,
                            "sell_value": None,
                        }
                    )
                by_label = {
                    market_series["label"]: market_series
                    for market_series in item["market_series"]
                }
                for market in family.get("markets", []):
                    if not isinstance(market, dict) or not market.get("label"):
                        continue
                    buy_price = market.get("buy_price")
                    sell_price = market.get("sell_price")
                    if isinstance(buy_price, (int, float)) and isinstance(sell_price, (int, float)):
                        probability = (float(buy_price) + float(sell_price)) / 2
                    elif isinstance(market.get("price"), (int, float)):
                        probability = float(market["price"])
                    else:
                        continue
                    market_series = by_label.get(market["label"])
                    if market_series is None:
                        market_series = {
                            "label": market["label"],
                            "points": [
                                {
                                    "index": index,
                                    "timestamp": None,
                                    "value": None,
                                    "buy_value": None,
                                    "sell_value": None,
                                }
                                for index in range(point_index + 1)
                            ],
                        }
                        item["market_series"].append(market_series)
                        by_label[market["label"]] = market_series
                    market_series["points"][point_index] = {
                        "index": point_index,
                        "timestamp": timestamp,
                        "value": probability,
                        "buy_value": float(buy_price) if isinstance(buy_price, (int, float)) else None,
                        "sell_value": float(sell_price) if isinstance(sell_price, (int, float)) else None,
                    }
            elif uses_basket_totals:
                markets = family.get("markets", [])
                buy_total = family.get("buy_total")
                sell_total = family.get("sell_total")
                if not isinstance(buy_total, (int, float)) and markets and all(
                    isinstance(market.get("buy_price"), (int, float)) for market in markets
                ):
                    buy_total = sum(float(market["buy_price"]) for market in markets)
                if not isinstance(sell_total, (int, float)) and markets and all(
                    isinstance(market.get("sell_price"), (int, float)) for market in markets
                ):
                    sell_total = sum(float(market["sell_price"]) for market in markets)
                basket_values = (
                    ("Buy all outcomes", buy_total),
                    ("Sell all outcomes", sell_total),
                )
                by_label = {entry["label"]: entry for entry in item["market_series"]}
                for label, basket_value in basket_values:
                    basket_series = by_label.get(label)
                    if basket_series is None:
                        basket_series = {"label": label, "points": []}
                        item["market_series"].append(basket_series)
                    basket_series["points"].append(
                        {
                            "index": point_index,
                            "timestamp": timestamp,
                            "value": float(basket_value) if isinstance(basket_value, (int, float)) else None,
                        }
                    )
    return {"snapshot_count": len(records), "families": list(series.values())}


def _next_cadence_start(previous_start: float, cadence_seconds: float, now: float) -> float:
    """Return the next future slot on a fixed cadence."""
    next_start = previous_start + cadence_seconds
    while next_start < now:
        next_start += cadence_seconds
    return next_start


def _partition_executable_families(
    families: list[dict], snapshot: dict
) -> tuple[list[dict], list[dict], list[dict]]:
    """Split registered families into executable, definitively illiquid, and unknown."""
    results_by_key = {
        (result.get("monitoring_key") or result.get("name")): result
        for result in snapshot.get("families", [])
        if isinstance(result, dict)
    }
    executable = []
    illiquid = []
    unknown = []
    for family in families:
        key = family.get("monitoring_key") or family.get("name")
        result = results_by_key.get(key, {})
        status = result.get("liquidity_status")
        if status == "executable":
            executable.append(family)
        elif status == "illiquid":
            illiquid.append(family)
        else:
            unknown.append(family)
    return executable, illiquid, unknown


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
        self.monitor_interval_minutes = DEFAULT_SNAPSHOT_INTERVAL_MINUTES
        self.next_snapshot_at: str | None = None
        self.discovery_limit = 10
        self.minimum_confidence = 0.8
        self.last_discovery_at: str | None = None
        self.next_discovery_at: str | None = None
        self.pending_events: list[dict] = []
        self.notifications: list[dict] = []
        self.notification_sequence = 0
        self.active_violation_families: set[str] = set()
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

    def start_discovery(
        self,
        limit: int,
        minimum_confidence: float,
        *,
        scheduled: bool = False,
    ) -> None:
        if not 1 <= limit <= 50:
            raise ValueError("Discovery limit must be between 1 and 50.")
        if not 0 <= minimum_confidence <= 1:
            raise ValueError("Minimum confidence must be between 0 and 1.")
        with self.lock:
            if not self.chatgpt.connected:
                raise ValueError("Connect your ChatGPT plan before discovering markets.")
            if self.discovery_thread and self.discovery_thread.is_alive():
                raise ValueError("Market discovery is already running.")
            if (
                not scheduled
                and self.next_discovery_at
                and datetime.fromisoformat(self.next_discovery_at) > datetime.now(timezone.utc)
            ):
                raise ValueError(
                    "The AI review runs once per hour. Wait until the next scheduled review."
                )
            if scheduled and self.pending_events:
                return
            self.discovery_limit = limit
            self.minimum_confidence = minimum_confidence
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
            for event in events:
                classification = event.get("classification") or {}
                event["approval_eligible"] = bool(
                    classification.get("relationship_found")
                    and classification.get("law") in PROBABILITY_LAWS
                )
                event["meets_confidence"] = (
                    float(classification.get("confidence") or 0)
                    >= minimum_confidence
                )
            report["monitoring"] = {"state": "pending_user_approval"}
            write_discovery_report(report, MONITORING_DIR / "latest_discovery.json")
            now = datetime.now(timezone.utc)
            with self.lock:
                self.pending_events = events
                self.last_discovery_at = now.isoformat()
                self.next_discovery_at = (
                    now + timedelta(hours=AI_DISCOVERY_INTERVAL_HOURS)
                ).isoformat()
                self.discovery.update(
                    state="awaiting_approval",
                    message=(
                        f"{len(events)} event group(s) are ready for your approval. "
                        "Nothing new will be monitored until you approve it."
                    ),
                )
        except Exception as error:  # Surface background failures in the UI.
            with self.lock:
                self.discovery.update(state="error", message=str(error))

    def approve_discovery(self, event_ids: list[str] | None = None) -> dict:
        with self.lock:
            wanted = None if event_ids is None else set(event_ids)
            selected = [
                event for event in self.pending_events
                if (wanted is None or str(event.get("event_id")) in wanted)
                and event.get("approval_eligible")
            ]
        if not selected:
            raise ValueError("Select at least one eligible event group to approve.")
        candidates = []
        event_by_key = {}
        for event in selected:
            family = family_from_classification(
                event,
                event.get("classification") or {},
                minimum_confidence=0,
                allow_review=True,
            )
            if family is not None:
                candidates.append(family)
                event_by_key[family["monitoring_key"]] = event
        snapshot = collect_snapshot(candidates) if candidates else {"families": []}
        executable, _illiquid, _unknown = _partition_executable_families(
            candidates, snapshot
        )
        executable_keys = {family["monitoring_key"] for family in executable}
        accepted_events = [event_by_key[key] for key in executable_keys]
        if accepted_events:
            summary = register_classified_events(
                accepted_events,
                registry_path=DEFAULT_MONITORING_REGISTRY,
                minimum_confidence=0,
                allow_review=True,
            )
        else:
            summary = {
                "accepted": [],
                "skipped": [],
                "family_count": len(load_monitored_families()),
                "registry_path": str(DEFAULT_MONITORING_REGISTRY),
            }
        selected_ids = {str(event.get("event_id")) for event in selected}
        skipped_ids = selected_ids - {
            key.removeprefix("polymarket:event:") for key in executable_keys
        }
        summary["unexecutable"] = sorted(skipped_ids)
        accepted_ids = {
            key.removeprefix("polymarket:event:") for key in summary["accepted"]
        }
        with self.lock:
            self.pending_events = [
                event for event in self.pending_events
                if str(event.get("event_id")) not in selected_ids
            ]
            self.discovery.update(
                state="awaiting_approval" if self.pending_events else "complete",
                message=(
                    f"Added {len(accepted_ids)} executable event group(s); "
                    f"skipped {len(skipped_ids)} without executable quotes. "
                    f"{len(self.pending_events)} still awaiting review."
                ),
            )
        return summary

    def dismiss_discovery(self) -> None:
        with self.lock:
            self.pending_events = []
            self.discovery.update(state="complete", message="Discovery review completed.")

    def start_monitoring(
        self,
        interval_minutes: float = DEFAULT_SNAPSHOT_INTERVAL_MINUTES,
    ) -> None:
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
            if not self.next_discovery_at:
                self.next_discovery_at = (
                    datetime.now(timezone.utc) + timedelta(hours=AI_DISCOVERY_INTERVAL_HOURS)
                ).isoformat()
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="antilego-monitor",
            )
            self.monitor_thread.start()

    def _monitor_loop(self) -> None:
        cadence_seconds = self.monitor_interval_minutes * 60
        scheduled_start = time.monotonic()
        try:
            while not self.monitor_stop.is_set():
                families = load_monitored_families()
                if not families:
                    raise RuntimeError("The monitoring registry is empty.")
                collected = collect_snapshot(families)
                executable, illiquid_families, unknown = _partition_executable_families(
                    families, collected
                )
                executable_keys = {
                    family.get("monitoring_key") or family.get("name")
                    for family in executable
                }
                snapshot = {
                    **collected,
                    "families": [
                        result for result in collected.get("families", [])
                        if (result.get("monitoring_key") or result.get("name"))
                        in executable_keys
                    ],
                }
                if illiquid_families:
                    retained = [
                        family for family in families if family not in illiquid_families
                    ]
                    write_monitored_families(retained)
                output_path = (
                    append_snapshot(snapshot) if snapshot["families"] else live_snapshot_path()
                )
                scheduled_start = _next_cadence_start(
                    scheduled_start,
                    cadence_seconds,
                    time.monotonic(),
                )
                wait_seconds = max(0.0, scheduled_start - time.monotonic())
                next_time = datetime.now(timezone.utc) + timedelta(seconds=wait_seconds)
                violations = sum(
                    family.get("violation_count", 0)
                    for family in snapshot.get("families", [])
                )
                self._record_violation_notifications(snapshot)
                with self.lock:
                    self.monitor_message = (
                        f"Saved {len(snapshot['families'])} family result(s) to "
                        f"{output_path.name}; {violations} executable violation(s), "
                        f"removed {len(illiquid_families)} unexecutable family/families, "
                        f"and deferred {len(unknown)} with temporarily unavailable data."
                    )
                    self.next_snapshot_at = next_time.isoformat()
                if not executable and not unknown:
                    with self.lock:
                        self.monitor_state = "stopped"
                        self.monitor_message = (
                            "No executable market families remain. Discover markets "
                            "again to find new opportunities."
                        )
                    return
                self._start_scheduled_discovery_if_due()
                if self.monitor_stop.wait(wait_seconds):
                    break
        except Exception as error:  # Surface background failures in the UI.
            with self.lock:
                self.monitor_state = "error"
                self.monitor_message = str(error)
                self.next_snapshot_at = None
        finally:
            with self.lock:
                if self.monitor_state == "running":
                    self.monitor_state = "stopped"
                    self.monitor_message = "Monitoring stopped."
                self.next_snapshot_at = None

    def _start_scheduled_discovery_if_due(self) -> None:
        with self.lock:
            due = self.next_discovery_at and datetime.fromisoformat(
                self.next_discovery_at
            ) <= datetime.now(timezone.utc)
            can_start = not self.pending_events and not (
                self.discovery_thread and self.discovery_thread.is_alive()
            )
            limit = self.discovery_limit
            confidence = self.minimum_confidence
        if due and can_start:
            self.start_discovery(limit, confidence, scheduled=True)

    def _record_violation_notifications(self, snapshot: dict) -> None:
        current = {
            str(family.get("name"))
            for family in snapshot.get("families", [])
            if family.get("coherent") is False
        }
        with self.lock:
            newly_violating = current - self.active_violation_families
            self.active_violation_families = current
        for name in sorted(newly_violating):
            family = next(
                item for item in snapshot.get("families", []) if item.get("name") == name
            )
            count = int(family.get("violation_count", 0))
            message = f"{name}: {count} probability-law violation(s) detected."
            with self.lock:
                self.notification_sequence += 1
                self.notifications.append(
                    {
                        "id": self.notification_sequence,
                        "timestamp": snapshot.get("timestamp"),
                        "title": "Antilego violation",
                        "message": message,
                        "family": name,
                    }
                )
                self.notifications = self.notifications[-50:]
            script = (
                "on run argv\n"
                "display notification (item 2 of argv) with title (item 1 of argv)\n"
                "end run"
            )
            try:
                subprocess.Popen(
                    ["/usr/bin/osascript", "-e", script, "Antilego violation", message],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                pass
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

    def clear_all_data(self) -> None:
        """Reset active dashboard data while preserving archived evidence files."""
        with self.lock:
            if self.monitor_thread and self.monitor_thread.is_alive():
                raise ValueError("Stop monitoring before clearing Antilego data.")
            if self.discovery_thread and self.discovery_thread.is_alive():
                raise ValueError("Wait for discovery to finish before clearing data.")
            if self.graph_thread and self.graph_thread.is_alive():
                raise ValueError("Wait for graph generation to finish before clearing data.")

            snapshot_path = live_snapshot_path()
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            with snapshot_path.open("a", encoding="utf-8") as snapshots:
                snapshots.write(
                    json.dumps(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "event": "dashboard_reset",
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
            write_monitored_families([], DEFAULT_MONITORING_REGISTRY)
            write_discovery_report(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "events": [],
                    "reset": True,
                },
                MONITORING_DIR / "latest_discovery.json",
            )

            self.pending_events = []
            self.notifications = []
            self.notification_sequence = 0
            self.active_violation_families = set()
            self.last_discovery_at = None
            self.next_discovery_at = None
            self.next_snapshot_at = None
            self.discovery = {
                "state": "idle",
                "message": "All discovered events and monitored markets were cleared.",
                "processed": 0,
                "total": 0,
            }
            self.graphs = {
                "state": "idle",
                "message": "Dashboard reset. Archived snapshots, reports, and graphs were preserved.",
            }
            self.monitor_state = "stopped"
            self.monitor_message = "Dashboard reset. Discover markets to begin again; prior files remain archived."

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
                    "polymarket_url": _polymarket_event_url(family),
                    "market_count": len(family.get("markets", [])),
                    "confidence": family.get("source", {}).get(
                        "classification_confidence"
                    ),
                    "coherent": latest.get("coherent"),
                    "data_complete": latest.get("data_complete"),
                    "liquidity_status": latest.get("liquidity_status"),
                    "target_shares": latest.get("target_shares"),
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
            pending = []
            for event in self.pending_events:
                classification = event.get("classification") or {}
                pending.append(
                    {
                        "event_id": str(event.get("event_id") or ""),
                        "title": event.get("title") or "Untitled event",
                        "contract_count": len(event.get("contracts", [])),
                        "volume": event.get("volume"),
                        "law": classification.get("law"),
                        "confidence": classification.get("confidence"),
                        "reason": classification.get("reason"),
                        "requires_review": bool(classification.get("requires_review")),
                        "eligible": bool(event.get("approval_eligible")),
                        "meets_confidence": bool(event.get("meets_confidence")),
                    }
                )
            return {
                "chatgpt": self.chatgpt.status(),
                "monitor": {
                    "state": self.monitor_state,
                    "message": self.monitor_message,
                    "interval_minutes": self.monitor_interval_minutes,
                    "next_snapshot_at": self.next_snapshot_at,
                },
                "discovery": dict(self.discovery),
                "discovery_schedule": {
                    "cadence_hours": AI_DISCOVERY_INTERVAL_HOURS,
                    "last_discovery_at": self.last_discovery_at,
                    "next_discovery_at": self.next_discovery_at,
                },
                "pending_events": pending,
                "graphs": {**self.graphs, "items": figures},
                "history": _snapshot_history(live_snapshot_path()),
                "notifications": list(self.notifications),
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
        color = "#ffffff" if success else "#ed6a6a"
        body = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(title)}</title>
<body style="margin:0;background:#050505;color:#f4f4f4;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif">
<main style="max-width:680px;margin:14vh auto;padding:32px;border:1px solid rgba(214,238,225,.18)">
<p style="color:{color};letter-spacing:.16em;text-transform:uppercase">Antilego / ChatGPT</p>
<h1 style="font-size:clamp(2.5rem,7vw,5rem);line-height:.92">{html.escape(title)}</h1>
<p style="color:#93a49b;font-size:1.05rem;line-height:1.7">{html.escape(message)}</p>
<a href="/" style="display:inline-block;margin-top:24px;padding:14px 18px;color:#050505;background:{color};text-decoration:none;font-weight:700">Return to Antilego</a>
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
            elif path == "/api/discovery/approve":
                event_ids = payload.get("event_ids")
                if not isinstance(event_ids, list):
                    raise ValueError("event_ids must be a list.")
                self.server.state.approve_discovery([str(value) for value in event_ids])
            elif path == "/api/discovery/approve-all":
                self.server.state.approve_discovery()
            elif path == "/api/discovery/dismiss":
                self.server.state.dismiss_discovery()
            elif path == "/api/monitor/start":
                self.server.state.start_monitoring(
                    float(payload.get("interval_minutes", DEFAULT_SNAPSHOT_INTERVAL_MINUTES))
                )
            elif path == "/api/monitor/stop":
                self.server.state.stop_monitoring()
            elif path == "/api/graphs":
                self.server.state.generate_graphs()
            elif path == "/api/open-folder":
                self.server.state.open_data_folder()
            elif path == "/api/clear-all":
                self.server.state.clear_all_data()
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
