"""AI-assisted classification of market relationships into Antilego laws."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

from .contradiction_brain import PROBABILITY_LAWS

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-5.6-terra"
SUPPORTED_LAWS = tuple(
    law for law in PROBABILITY_LAWS if law != "mutually_exclusive"
)

SYSTEM_INSTRUCTIONS = """
You classify relationships among prediction-market contracts for Antilego.
Choose exactly one supported probability law, or return no_relationship.
Never invent a law or infer facts not stated in the contract titles and rules.
Contracts must share compatible settlement semantics and resolution criteria.
Return contract IDs in the exact logical order required by the selected law.

Law meanings:
- deadline_nesting: same event, ordered earlier to later deadline.
- threshold_chain: same measurement, ordered easier to harder threshold.
- exhaustive_outcomes: mutually exclusive outcomes that collectively cover every result.
- complements: exactly A and not-A for the same proposition.
- non_exhaustive_exclusivity: outcomes cannot co-occur but do not cover every result.
- logical_implication: ordered A then B where A logically implies B.

Use requires_review=true whenever wording, resolution rules, exhaustiveness,
ordering, or event identity is ambiguous. Confidence is between 0 and 1.
""".strip()

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "relationship_found",
        "law",
        "ordered_contract_ids",
        "confidence",
        "requires_review",
        "reason",
    ],
    "properties": {
        "relationship_found": {"type": "boolean"},
        "law": {"type": ["string", "null"], "enum": [*SUPPORTED_LAWS, None]},
        "ordered_contract_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "requires_review": {"type": "boolean"},
        "reason": {"type": "string"},
    },
}

Transport = Callable[[dict, str], dict]


@dataclass(frozen=True)
class RelationshipClassification:
    relationship_found: bool
    law: str | None
    ordered_contract_ids: tuple[str, ...]
    confidence: float
    requires_review: bool
    reason: str

    def to_dict(self) -> dict:
        return {
            "relationship_found": self.relationship_found,
            "law": self.law,
            "ordered_contract_ids": list(self.ordered_contract_ids),
            "confidence": self.confidence,
            "requires_review": self.requires_review,
            "reason": self.reason,
        }


def _validate_contracts(contracts: list[dict]) -> None:
    if len(contracts) < 2:
        raise ValueError("At least two contracts are required for relationship analysis")
    ids = []
    for contract in contracts:
        for field in ("id", "title", "rules"):
            if not isinstance(contract.get(field), str) or not contract[field].strip():
                raise ValueError(f"Every contract requires a non-empty {field!r}")
        ids.append(contract["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Contract IDs must be unique")


def validate_classification(payload: dict, contracts: list[dict]) -> RelationshipClassification:
    """Reject model output that cannot safely route into the deterministic engine."""
    _validate_contracts(contracts)
    relationship_found = payload.get("relationship_found")
    law = payload.get("law")
    ordered_ids = payload.get("ordered_contract_ids")
    confidence = payload.get("confidence")
    requires_review = payload.get("requires_review")
    reason = payload.get("reason")

    if not isinstance(relationship_found, bool):
        raise ValueError("relationship_found must be boolean")
    if law is not None and law not in SUPPORTED_LAWS:
        raise ValueError(f"Unsupported probability law returned by model: {law}")
    if not isinstance(ordered_ids, list) or not all(isinstance(i, str) for i in ordered_ids):
        raise ValueError("ordered_contract_ids must be a list of strings")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("confidence must be numeric")
    if not 0 <= float(confidence) <= 1:
        raise ValueError("confidence must be between zero and one")
    if not isinstance(requires_review, bool) or not isinstance(reason, str):
        raise ValueError("requires_review and reason have invalid types")

    supplied_ids = {contract["id"] for contract in contracts}
    if relationship_found:
        if law is None:
            raise ValueError("A detected relationship requires a law")
        if len(ordered_ids) < 2 or len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("A relationship requires at least two unique ordered contracts")
        if not set(ordered_ids).issubset(supplied_ids):
            raise ValueError("Model returned an unknown contract ID")
        if law == "complements" and len(ordered_ids) != 2:
            raise ValueError("Complementarity requires exactly two contracts")
    elif law is not None or ordered_ids:
        raise ValueError("No-relationship output cannot select a law or contracts")

    return RelationshipClassification(
        relationship_found=relationship_found,
        law=law,
        ordered_contract_ids=tuple(ordered_ids),
        confidence=float(confidence),
        requires_review=requires_review,
        reason=reason.strip(),
    )


def _extract_output_text(response: dict) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]
    for item in response.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise RuntimeError("OpenAI response did not contain structured output text")


def openai_transport(request_payload: dict, api_key: str) -> dict:
    request = urllib.request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(request_payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Antilego/1.0 (relationship research)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API request failed ({error.code}): {detail}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"OpenAI API request failed: {error}") from error


def classify_relationship(
    contracts: list[dict],
    *,
    model: str | None = None,
    api_key: str | None = None,
    transport: Transport = openai_transport,
) -> RelationshipClassification:
    """Classify supplied contract metadata and validate the model's proposal."""
    _validate_contracts(contracts)
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set OPENAI_API_KEY before running AI classification")
    model = model or os.getenv("ANTILEGO_OPENAI_MODEL", DEFAULT_MODEL)
    request_payload = {
        "model": model,
        "instructions": SYSTEM_INSTRUCTIONS,
        "input": json.dumps({"contracts": contracts}, ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "antilego_relationship_classification",
                "strict": True,
                "schema": CLASSIFICATION_SCHEMA,
            }
        },
    }
    response = transport(request_payload, api_key)
    try:
        payload = json.loads(_extract_output_text(response))
    except json.JSONDecodeError as error:
        raise RuntimeError("Model returned invalid JSON") from error
    return validate_classification(payload, contracts)
