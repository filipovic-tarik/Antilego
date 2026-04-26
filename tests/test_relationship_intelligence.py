import json
import unittest

from antilego.relationship_intelligence import (
    SUPPORTED_LAWS,
    classify_relationship,
    validate_classification,
)


CONTRACTS = [
    {
        "id": "september",
        "title": "Fed cut by September?",
        "rules": "Yes if a rate cut occurs on or before the September meeting.",
    },
    {
        "id": "december",
        "title": "Fed cut by December?",
        "rules": "Yes if a rate cut occurs on or before the December meeting.",
    },
]


class RelationshipIntelligenceTests(unittest.TestCase):
    def test_classifier_uses_strict_schema_and_validates_result(self):
        captured = {}

        def fake_transport(request, api_key):
            captured["request"] = request
            captured["api_key"] = api_key
            return {
                "output_text": json.dumps(
                    {
                        "relationship_found": True,
                        "law": "deadline_nesting",
                        "ordered_contract_ids": ["september", "december"],
                        "confidence": 0.98,
                        "requires_review": False,
                        "reason": "The same event is measured at nested deadlines.",
                    }
                )
            }

        result = classify_relationship(
            CONTRACTS,
            api_key="test-key",
            model="test-model",
            transport=fake_transport,
        )

        self.assertEqual(result.law, "deadline_nesting")
        self.assertEqual(result.ordered_contract_ids, ("september", "december"))
        self.assertEqual(captured["api_key"], "test-key")
        self.assertEqual(captured["request"]["model"], "test-model")
        self.assertTrue(captured["request"]["text"]["format"]["strict"])

    def test_model_cannot_invent_probability_law(self):
        with self.assertRaisesRegex(ValueError, "Unsupported probability law"):
            validate_classification(
                {
                    "relationship_found": True,
                    "law": "bayes_magic",
                    "ordered_contract_ids": ["september", "december"],
                    "confidence": 0.9,
                    "requires_review": False,
                    "reason": "Invented.",
                },
                CONTRACTS,
            )

    def test_model_cannot_return_unknown_contract(self):
        with self.assertRaisesRegex(ValueError, "unknown contract ID"):
            validate_classification(
                {
                    "relationship_found": True,
                    "law": "deadline_nesting",
                    "ordered_contract_ids": ["september", "invented"],
                    "confidence": 0.9,
                    "requires_review": False,
                    "reason": "Invalid ID.",
                },
                CONTRACTS,
            )

    def test_no_relationship_has_no_law_or_ordering(self):
        result = validate_classification(
            {
                "relationship_found": False,
                "law": None,
                "ordered_contract_ids": [],
                "confidence": 0.8,
                "requires_review": False,
                "reason": "Contracts describe unrelated events.",
            },
            CONTRACTS,
        )
        self.assertFalse(result.relationship_found)
        self.assertIsNone(result.law)

    def test_complements_require_exactly_two_contracts(self):
        three_contracts = CONTRACTS + [
            {"id": "june", "title": "Fed cut by June?", "rules": "June rules"}
        ]
        with self.assertRaisesRegex(ValueError, "exactly two"):
            validate_classification(
                {
                    "relationship_found": True,
                    "law": "complements",
                    "ordered_contract_ids": ["june", "september", "december"],
                    "confidence": 0.7,
                    "requires_review": True,
                    "reason": "Invalid complement group.",
                },
                three_contracts,
            )

    def test_supported_laws_match_engine_vocabulary(self):
        self.assertIn("deadline_nesting", SUPPORTED_LAWS)
        self.assertIn("logical_implication", SUPPORTED_LAWS)
        self.assertNotIn("mutually_exclusive", SUPPORTED_LAWS)


if __name__ == "__main__":
    unittest.main()
