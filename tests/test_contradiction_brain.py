import unittest

from antilego.contradiction_brain import PROBABILITY_LAWS, evaluate_family


class ContradictionBrainTests(unittest.TestCase):
    def test_deadline_nesting_violation(self):
        result = evaluate_family(
            {
                "type": "deadline_nesting",
                "markets": [
                    {"label": "September", "price": 0.75},
                    {"label": "October", "price": 0.63},
                ],
            }
        )
        self.assertFalse(result["coherent"])
        self.assertEqual(result["violation_count"], 1)
        self.assertAlmostEqual(result["violations"][0]["magnitude"], 0.12)

    def test_threshold_chain_coherent(self):
        result = evaluate_family(
            {
                "type": "threshold_chain",
                "markets": [
                    {"label": "$80k", "price": 0.7},
                    {"label": "$90k", "price": 0.4},
                ],
            }
        )
        self.assertTrue(result["coherent"])

    def test_exclusive_sum_violation(self):
        result = evaluate_family(
            {
                "type": "mutually_exclusive",
                "markets": [
                    {"label": "A", "price": 0.6},
                    {"label": "B", "price": 0.5},
                ],
            }
        )
        self.assertFalse(result["coherent"])
        self.assertAlmostEqual(result["sum"], 1.1)

    def test_exhaustive_outcomes_detect_underround(self):
        result = evaluate_family(
            {
                "type": "exhaustive_outcomes",
                "markets": [
                    {"label": "A", "price": 0.4},
                    {"label": "B", "price": 0.5},
                ],
            }
        )
        self.assertFalse(result["coherent"])
        self.assertAlmostEqual(result["sum"], 0.9)

    def test_complements_must_sum_to_one(self):
        result = evaluate_family(
            {
                "type": "complements",
                "markets": [
                    {"label": "A", "price": 0.62},
                    {"label": "not A", "price": 0.43},
                ],
            }
        )
        self.assertFalse(result["coherent"])
        self.assertAlmostEqual(result["sum"], 1.05)

    def test_non_exhaustive_exclusivity_allows_sum_below_one(self):
        coherent = evaluate_family(
            {
                "type": "non_exhaustive_exclusivity",
                "markets": [
                    {"label": "A", "price": 0.3},
                    {"label": "B", "price": 0.4},
                ],
            }
        )
        violated = evaluate_family(
            {
                "type": "non_exhaustive_exclusivity",
                "markets": [
                    {"label": "A", "price": 0.6},
                    {"label": "B", "price": 0.5},
                ],
            }
        )
        self.assertTrue(coherent["coherent"])
        self.assertFalse(violated["coherent"])

    def test_logical_implication_probability_bound(self):
        result = evaluate_family(
            {
                "type": "logical_implication",
                "markets": [
                    {"label": "A", "price": 0.71},
                    {"label": "B", "price": 0.63},
                ],
            }
        )
        self.assertFalse(result["coherent"])
        self.assertEqual(result["violations"][0]["pair"], "A > B")

    def test_probability_law_registry_is_explicit(self):
        self.assertIn("deadline_nesting", PROBABILITY_LAWS)
        self.assertIn("threshold_chain", PROBABILITY_LAWS)
        self.assertIn("exhaustive_outcomes", PROBABILITY_LAWS)
        self.assertIn("complements", PROBABILITY_LAWS)
        self.assertIn("non_exhaustive_exclusivity", PROBABILITY_LAWS)
        self.assertIn("logical_implication", PROBABILITY_LAWS)

    def test_unsupported_law_is_not_reported_as_coherent(self):
        result = evaluate_family(
            {
                "type": "invented_law",
                "markets": [{"label": "A", "price": 0.5}],
            }
        )
        self.assertIsNone(result["coherent"])
        self.assertFalse(result["law_supported"])

    def test_missing_price_is_not_reported_as_coherent(self):
        result = evaluate_family(
            {
                "type": "deadline_nesting",
                "markets": [
                    {"label": "September", "price": 0.75},
                    {"label": "October", "price": None},
                ],
            }
        )
        self.assertIsNone(result["coherent"])
        self.assertFalse(result["data_complete"])


if __name__ == "__main__":
    unittest.main()
