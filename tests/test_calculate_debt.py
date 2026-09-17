from __future__ import annotations

import importlib.util
import unittest
from decimal import Decimal
from pathlib import Path
from fixtures import prospective_case


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "calculate_debt.py"
SPEC = importlib.util.spec_from_file_location("calculate_debt", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class ProspectiveCalculatorTests(unittest.TestCase):
    def test_missing_fee_rules_remain_unknown(self) -> None:
        case = {"case_name": "模拟", "principal": 1000, "term_months": 12,
                "annual_interest_rate_pct": 12, "overdue_snapshots_days": [30]}
        result = MODULE.calculate(case)
        self.assertEqual(result["status"], "simulation")
        self.assertEqual(len(result["unknown_cost_items"]), 3)
        self.assertEqual(result["overdue_snapshots"][0]["penalty_interest"], Decimal("0.00"))

    def test_acceleration_on_requested_checkpoint_is_shown(self) -> None:
        case = {"case_name": "模拟", "principal": 1000, "term_months": 12,
                "annual_interest_rate_pct": 12, "overdue_snapshots_days": [30],
                "acceleration": {"possible_after_days": 30}}
        result = MODULE.calculate(case)
        self.assertIn("风险跳点", MODULE.markdown(result))

    def test_non_finite_principal_is_rejected(self) -> None:
        case = {"case_name": "模拟", "principal": "NaN", "term_months": 12,
                "annual_interest_rate_pct": 12, "overdue_snapshots_days": [30]}
        with self.assertRaises(ValueError):
            MODULE.calculate(case)

    def test_public_example_remains_stable(self) -> None:
        data = prospective_case()

        result = MODULE.calculate(data)

        self.assertEqual(result["origination"]["normal_total_repayment"], Decimal("11601.60"))
        self.assertEqual(result["overdue_snapshots"][0]["known_due_total"], Decimal("999.14"))

    def test_unsupported_repayment_method_is_rejected(self) -> None:
        data = {
            "case_name": "测试",
            "principal": 1000,
            "term_months": 1,
            "annual_interest_rate_pct": 12,
            "overdue_snapshots_days": [30],
            "repayment_method": "interest_only",
        }

        with self.assertRaisesRegex(ValueError, "equal_payment only"):
            MODULE.calculate(data)


if __name__ == "__main__":
    unittest.main()
