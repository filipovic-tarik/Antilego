import json
import tempfile
import unittest
from pathlib import Path

from antilego.monitoring_registry import (
    family_from_classification,
    load_monitored_families,
    register_classified_events,
)


EVENT = {
    "event_id": "event-1",
    "event_slug": "event-one",
    "title": "Event One",
    "contracts": [
        {
            "id": "early",
            "title": "By September?",
            "label": "September",
            "asset_id": "asset-early",
            "market_slug": "by-september",
        },
        {
            "id": "late",
            "title": "By December?",
            "label": "December",
            "asset_id": "asset-late",
            "market_slug": "by-december",
        },
    ],
}

APPROVED = {
    "relationship_found": True,
    "law": "deadline_nesting",
    "ordered_contract_ids": ["early", "late"],
    "confidence": 0.94,
    "requires_review": False,
    "reason": "The same outcome is measured at nested deadlines.",
}


class MonitoringRegistryTests(unittest.TestCase):
    def test_approved_classification_becomes_collector_family(self):
        family = family_from_classification(EVENT, APPROVED)
        self.assertEqual(family["type"], "deadline_nesting")
        self.assertEqual(family["monitoring_key"], "polymarket:event:event-1")
        self.assertEqual(
            [market["asset_id"] for market in family["markets"]],
            ["asset-early", "asset-late"],
        )

    def test_review_and_low_confidence_results_are_not_registered(self):
        review = {**APPROVED, "requires_review": True}
        low_confidence = {**APPROVED, "confidence": 0.5}
        self.assertIsNone(family_from_classification(EVENT, review))
        self.assertIsNone(family_from_classification(EVENT, low_confidence))
        self.assertIsNone(
            family_from_classification(EVENT, {**APPROVED, "law": "invented_law"})
        )

    def test_explicit_user_approval_can_accept_review_flag(self):
        review = {**APPROVED, "requires_review": True, "confidence": 0.55}
        family = family_from_classification(
            EVENT,
            review,
            minimum_confidence=0,
            allow_review=True,
        )
        self.assertEqual(family["monitoring_key"], "polymarket:event:event-1")

    def test_register_upserts_same_event_instead_of_duplicating(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "monitoring.json"
            event = {**EVENT, "classification": APPROVED}
            first = register_classified_events([event], registry_path=registry)
            second = register_classified_events([event], registry_path=registry)
            families = load_monitored_families(registry)

        self.assertEqual(first["family_count"], 1)
        self.assertEqual(second["family_count"], 1)
        self.assertEqual(len(families), 1)

    def test_event_without_classification_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "monitoring.json"
            result = register_classified_events([EVENT], registry_path=registry)
        self.assertEqual(result["accepted"], [])
        self.assertEqual(result["skipped"], ["event-1"])

    def test_registry_is_versioned_json(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = Path(directory) / "monitoring.json"
            register_classified_events(
                [{**EVENT, "classification": APPROVED}],
                registry_path=registry,
            )
            payload = json.loads(registry.read_text(encoding="utf-8"))
        self.assertEqual(payload["version"], 1)
        self.assertIn("updated_at", payload)


if __name__ == "__main__":
    unittest.main()
