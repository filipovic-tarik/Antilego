"""Persistent registry for approved, dynamically discovered market families."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .contradiction_brain import PROBABILITY_LAWS
from .paths import DEFAULT_MONITORING_REGISTRY

REGISTRY_VERSION = 1


def _classification_dict(classification: object) -> dict:
    if hasattr(classification, "to_dict"):
        classification = classification.to_dict()
    if not isinstance(classification, dict):
        raise TypeError("classification must be a dictionary or classification result")
    return classification


def family_from_classification(
    event: dict,
    classification: object,
    *,
    minimum_confidence: float = 0.8,
    allow_review: bool = False,
) -> dict | None:
    """Convert one approved classification into a collector-ready family."""
    classification = _classification_dict(classification)
    if not classification.get("relationship_found"):
        return None
    if classification.get("requires_review") and not allow_review:
        return None
    confidence = classification.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        return None
    if float(confidence) < minimum_confidence:
        return None

    law = classification.get("law")
    ordered_ids = classification.get("ordered_contract_ids")
    if law not in PROBABILITY_LAWS or not isinstance(ordered_ids, list):
        return None
    contract_by_id = {
        str(contract.get("id")): contract
        for contract in event.get("contracts", [])
        if isinstance(contract, dict)
    }
    if len(ordered_ids) < 2 or len(ordered_ids) != len(set(ordered_ids)):
        return None
    if any(contract_id not in contract_by_id for contract_id in ordered_ids):
        return None

    markets = []
    for contract_id in ordered_ids:
        contract = contract_by_id[contract_id]
        asset_id = str(contract.get("asset_id", "")).strip()
        label = str(contract.get("label") or contract.get("title") or "").strip()
        if not asset_id or not label:
            return None
        markets.append(
            {
                "label": label,
                "asset_id": asset_id,
                "contract_id": contract_id,
                "market_slug": str(contract.get("market_slug") or ""),
            }
        )

    event_id = str(event.get("event_id", "")).strip()
    title = str(event.get("title", "")).strip()
    if not event_id or not title:
        return None
    return {
        "monitoring_key": f"polymarket:event:{event_id}",
        "name": title,
        "type": law,
        "constraint": str(classification.get("reason") or law),
        "source": {
            "provider": "polymarket",
            "event_id": event_id,
            "event_slug": str(event.get("event_slug") or ""),
            "classification_confidence": float(confidence),
        },
        "markets": markets,
    }


def load_monitored_families(
    registry_path: Path = DEFAULT_MONITORING_REGISTRY,
) -> list[dict]:
    """Load approved families, returning an empty list before first registration."""
    registry_path = Path(registry_path)
    if not registry_path.exists():
        return []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("version") != REGISTRY_VERSION:
        raise ValueError("Unsupported monitoring registry format")
    families = payload.get("families")
    if not isinstance(families, list):
        raise ValueError("Monitoring registry must contain a families array")
    return families


def write_monitored_families(
    families: list[dict],
    registry_path: Path = DEFAULT_MONITORING_REGISTRY,
) -> Path:
    """Atomically replace the monitoring registry."""
    registry_path = Path(registry_path)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": REGISTRY_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "families": families,
    }
    temporary_path = registry_path.with_suffix(f"{registry_path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(registry_path)
    return registry_path.resolve()


def register_classified_events(
    events: list[dict],
    *,
    registry_path: Path = DEFAULT_MONITORING_REGISTRY,
    minimum_confidence: float = 0.8,
    allow_review: bool = False,
) -> dict:
    """Upsert approved event classifications and report what was skipped."""
    if not 0 <= minimum_confidence <= 1:
        raise ValueError("minimum_confidence must be between zero and one")
    families = load_monitored_families(registry_path)
    family_by_key = {
        family.get("monitoring_key"): family
        for family in families
        if isinstance(family, dict) and family.get("monitoring_key")
    }
    accepted = []
    skipped = []
    for event in events:
        classification = event.get("classification")
        if not isinstance(classification, dict) and not hasattr(classification, "to_dict"):
            skipped.append(str(event.get("event_id") or event.get("title") or "unknown"))
            continue
        family = family_from_classification(
            event,
            classification,
            minimum_confidence=minimum_confidence,
            allow_review=allow_review,
        )
        if family is None:
            skipped.append(str(event.get("event_id") or event.get("title") or "unknown"))
            continue
        family_by_key[family["monitoring_key"]] = family
        accepted.append(family["monitoring_key"])

    ordered_families = sorted(family_by_key.values(), key=lambda family: family["name"])
    output_path = write_monitored_families(ordered_families, registry_path)
    return {
        "accepted": accepted,
        "skipped": skipped,
        "family_count": len(ordered_families),
        "registry_path": str(output_path),
    }
