import unittest

from antilego.contradiction_brain import evaluate_family


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
