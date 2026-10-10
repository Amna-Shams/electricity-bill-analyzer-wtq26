"""Offline unit tests (no API calls):  python -m unittest discover -s tests -v"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import calc  # noqa: E402
from schemas import Bill, null_bill  # noqa: E402

BILL = json.loads((ROOT / "expected_KESC_0008.json").read_text(encoding="utf-8"))
USAGE = [{"month": m, "units": u} for m, u in [
    ("2025-04", 141), ("2025-05", 138), ("2025-06", 197), ("2025-07", 239), ("2025-08", 203), ("2025-09", 176),
    ("2025-10", 173), ("2025-11", 187), ("2025-12", 124), ("2026-01", 96), ("2026-02", 88), ("2026-03", 115),
    ("2026-04", 151)]]


class CalcTests(unittest.TestCase):
    def test_taxes_percent(self):
        self.assertEqual(calc.bill_breakdown(BILL)["taxes_percent_of_current_bill"], 16.61)

    def test_threshold_count_matches_guide_example(self):
        s = calc.question_specific("How many months went above 200 units?", USAGE, "2026-04", BILL)
        t = s["unit_thresholds"][0]
        self.assertEqual(t["previous_months_above"], 2)            # July 2025 (239), August 2025 (203)
        self.assertEqual(t["count_above_including_current_month"], 2)

    def test_usage_excludes_current_month(self):
        u = calc.usage_stats(USAGE, "2026-04", 151)
        self.assertEqual(u["previous_months_count"], 12)
        self.assertEqual(u["highest_previous_month"]["units"], 239)
        self.assertEqual(u["lowest_previous_month"]["units"], 88)

    def test_late_payment_extra(self):
        self.assertEqual(calc.bill_breakdown(BILL)["late_payment_extra_amount"], 286)


class NetMeteringTests(unittest.TestCase):
    ROWS = [{"month": "2025-07", "units": 781}, {"month": "2025-08", "units": 225}, {"month": "2025-09", "units": -142},
            {"month": "2026-06", "units": -152}]
    BILL = {"bill_month": "2026-07", "units_consumed": 1017, "current_bill": 20726}

    def test_negative_units_flagged_and_percent_withheld(self):
        u = calc.usage_stats(self.ROWS, "2026-07", 1017)
        self.assertTrue(u["has_negative_units"])
        self.assertIsNone(u["current_vs_most_recent_previous"]["percent_change"])   # base is negative
        self.assertEqual(u["current_vs_highest_previous"]["difference_units"], 236)  # 1017 - 781

    def test_estimates_suppressed_for_negative_history(self):
        stats = calc.build_stats(self.BILL, {"usage_history": self.ROWS, "billing_history": []}, {})
        self.assertIn("estimates_unavailable", stats["estimates"])
        self.assertNotIn("ESTIMATE_bill_at_average_previous_usage", stats["estimates"])

    def test_normal_history_still_estimates(self):
        stats = calc.build_stats(BILL, {"usage_history": USAGE, "billing_history": []}, {})
        self.assertEqual(stats["estimates"]["ESTIMATE_bill_at_average_previous_usage"], 3553.29)


class SchemaTests(unittest.TestCase):
    def test_expected_json_validates(self):
        self.assertEqual(Bill.model_validate(BILL).to_json_dict(), BILL)

    def test_null_bill_has_every_key(self):
        n = null_bill("KE")
        self.assertEqual(set(n), set(Bill.model_fields))
        self.assertEqual(n["charges"], [])


if __name__ == "__main__":
    unittest.main()
