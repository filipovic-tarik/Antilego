"""Discover currently tradable Polymarket contract groups from the Gamma API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

GAMMA_EVENTS_URL = "https://gamma-api.polymarket.com/events"
EventFetcher = Callable[[int, int], list[dict]]


def _json_list(value: object) -> list[str]:
    """Normalize Gamma fields that may be JSON strings or native lists."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _number(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def fetch_active_events(
    limit: int = 100,
    offset: int = 0,
    timeout: float = 20,
) -> list[dict]:
    """Fetch one volume-ranked page of open events from Polymarket Gamma."""
    query = urllib.parse.urlencode(
        {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "offset": offset,
            "order": "volume24hr",
            "ascending": "false",
        }
    )
    request = urllib.request.Request(
        f"{GAMMA_EVENTS_URL}?{query}",
        headers={"User-Agent": "Antilego/1.0 (read-only research)"},
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == 2:
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Polymarket discovery failed ({error.code}): {detail}"
                ) from error
        except (OSError, json.JSONDecodeError) as error:
            last_error = error
            if attempt == 2:
                raise RuntimeError(
                    f"Polymarket discovery could not reach Gamma API: {error}"
                ) from error
        time.sleep(0.75 * (attempt + 1))
    else:  # Defensive; the loop either breaks or raises.
        raise RuntimeError(f"Polymarket discovery failed: {last_error}")
    if not isinstance(payload, list):
        raise RuntimeError("Polymarket event discovery returned an unexpected payload")
    return payload


def contract_from_market(market: dict) -> dict | None:
    """Return classifier-ready metadata for one tradable binary YES/NO market."""
    if market.get("active") is False or market.get("closed") is True:
        return None
    if market.get("acceptingOrders") is False or market.get("enableOrderBook") is False:
        return None

    outcomes = _json_list(market.get("outcomes"))
    token_ids = _json_list(market.get("clobTokenIds"))
    if len(outcomes) != 2 or len(token_ids) != 2:
        return None
    normalized_outcomes = [outcome.strip().casefold() for outcome in outcomes]
    if set(normalized_outcomes) != {"yes", "no"}:
        return None

    yes_index = normalized_outcomes.index("yes")
    market_id = str(market.get("id", "")).strip()
    title = str(market.get("question", "")).strip()
    rules = str(market.get("description", "")).strip()
    asset_id = token_ids[yes_index].strip()
    if not all((market_id, title, rules, asset_id)):
        return None

    return {
        "id": market_id,
        "title": title,
        "rules": rules,
        "label": str(market.get("groupItemTitle") or title).strip(),
        "asset_id": asset_id,
        "market_slug": str(market.get("slug") or ""),
        "volume_24h": _number(market.get("volume24hr")),
        "liquidity": _number(market.get("liquidityNum", market.get("liquidity"))),
    }


def candidate_from_event(
    event: dict,
    *,
    min_contracts: int = 2,
    max_contracts: int = 40,
) -> dict | None:
    """Build one relationship-classification candidate from an active event."""
    contracts = [
        contract
        for market in event.get("markets", [])
        if isinstance(market, dict)
        for contract in [contract_from_market(market)]
        if contract is not None
    ]
    contracts.sort(
        key=lambda contract: (contract["volume_24h"], contract["liquidity"]),
        reverse=True,
    )
    if len(contracts) < min_contracts:
        return None
    contracts = contracts[:max_contracts]
    event_id = str(event.get("id", "")).strip()
    title = str(event.get("title", "")).strip()
    if not event_id or not title:
        return None
    return {
        "event_id": event_id,
        "event_slug": str(event.get("slug") or ""),
        "title": title,
        "volume_24h": _number(event.get("volume24hr")),
        "liquidity": _number(event.get("liquidity")),
        "contracts": contracts,
    }


def discover_active_market_groups(
    *,
    limit: int = 10,
    min_contracts: int = 2,
    max_contracts: int = 40,
    page_size: int = 100,
    max_pages: int = 10,
    fetcher: EventFetcher = fetch_active_events,
) -> list[dict]:
    """Return volume-ranked active events containing related binary contracts."""
    if min(limit, min_contracts, max_contracts, page_size, max_pages) <= 0:
        raise ValueError("Discovery limits must be positive")
    if min_contracts > max_contracts:
        raise ValueError("min_contracts cannot exceed max_contracts")

    candidates: list[dict] = []
    seen_event_ids: set[str] = set()
    for page_index in range(max_pages):
        events = fetcher(page_size, page_index * page_size)
        if not events:
            break
        for event in events:
            if not isinstance(event, dict):
                continue
            candidate = candidate_from_event(
                event,
                min_contracts=min_contracts,
                max_contracts=max_contracts,
            )
            if candidate is None or candidate["event_id"] in seen_event_ids:
                continue
            seen_event_ids.add(candidate["event_id"])
            candidates.append(candidate)
            if len(candidates) >= limit:
                return candidates
        if len(events) < page_size:
            break
    return candidates


def discovery_report(**kwargs: object) -> dict:
    """Return a serializable report of current discovery candidates."""
    candidates = discover_active_market_groups(**kwargs)
    return {
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "source": GAMMA_EVENTS_URL,
        "candidate_count": len(candidates),
        "events": candidates,
    }


def write_discovery_report(report: dict, output_path: Path) -> Path:
    """Write a discovery report atomically and return its resolved path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(f"{output_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(output_path)
    return output_path.resolve()
