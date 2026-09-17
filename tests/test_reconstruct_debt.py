from __future__ import annotations

import importlib.util
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from fixtures import complete_ledger_case


SCRIPT = Path(__file__).parents[1] / "scripts" / "reconstruct_debt.py"
ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("reconstruct_debt", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def base_case() -> dict:
    return {
        "case_name": "测试案例",
        "as_of_date": "2026-01-04",
        "amount_received": 1000,
        "normal_schedule_complete": True,
        "scheduled_payments": [
            {
                "id": "p1",
                "due_date": "2026-01-01",
                "components": {"principal": 1000},
                "status": "confirmed",
            }
        ],
        "allocation_order": ["penalty_interest", "normal_interest", "principal"],
        "fee_rules": [
            {
                "id": "penalty",
                "label": "逾期罚息",
                "category": "penalty_interest",
                "base": "overdue_principal",
                "rate_unit": "annual_pct",
                "rate_value": 36.5,
                "start_after_days": 0,
                "status": "confirmed",
                "source": "测试协议第1条",
            }
        ],
    }


class ReconstructionTests(unittest.TestCase):
    def test_post_compensation_opening_balance_accrues_recovery_fee(self) -> None:
        case = {
            "case_name": "代偿后账本",
            "case_scope": "post_compensation_recovery",
            "as_of_date": "2021-04-25",
            "amount_received": 5000,
            "opening_balance": {
                "date": "2021-04-24",
                "components": {"principal": 4188.34, "normal_interest": 121.86},
                "status": "confirmed",
                "evidence_type": "court_finding",
                "source": "判决认定的代偿构成",
            },
            "fee_rules": [{
                "category": "liquidated_damages",
                "base": "outstanding_principal",
                "rate_unit": "daily_pct",
                "rate_value": 0.03,
                "starts_on": "2021-04-24",
                "status": "confirmed",
                "source": "判决认定的追偿费率",
            }],
        }

        result = MODULE.calculate(case)

        self.assertEqual(result["as_of"]["amount_due_now"], Decimal("4311.46"))
        self.assertEqual(result["as_of"]["due_now"]["liquidated_damages"], Decimal("1.26"))
        self.assertIsNone(result["cost_analysis"]["normal_financing_cost"])
        self.assertIsNone(result["cost_analysis"]["all_in_annualized_cost_pct"])

    def test_payment_on_due_date_has_no_overdue_fee(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-02"
        case["transactions"] = [{"id": "r1", "date": "2026-01-01", "type": "repayment", "amount": 1000}]

        result = MODULE.calculate(case)["as_of"]

        self.assertEqual(result["amount_due_now"], Decimal("0.00"))
        self.assertEqual(result["remaining_principal"], Decimal("0.00"))
        self.assertNotIn("penalty_interest", result["due_now"])

    def test_late_payment_pays_three_days_penalty_then_principal(self) -> None:
        case = base_case()
        case["transactions"] = [{"id": "r1", "date": "2026-01-04", "type": "repayment", "amount": 503}]

        result = MODULE.calculate(case)["as_of"]

        self.assertEqual(result["amount_due_now"], Decimal("500.00"))
        self.assertEqual(result["remaining_principal"], Decimal("500.00"))
        allocation = result["payment_allocations"][0]["allocations"]
        penalty_paid = sum((item["amount"] for item in allocation if item["category"] == "penalty_interest"), Decimal("0"))
        principal_paid = sum((item["amount"] for item in allocation if item["category"] == "principal"), Decimal("0"))
        self.assertEqual(penalty_paid, Decimal("3.000"))
        self.assertEqual(principal_paid, Decimal("500.000"))

    def test_contract_allocation_order_controls_partial_payment(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-02"
        case["scheduled_payments"][0]["components"]["normal_interest"] = 100
        case["allocation_order"] = ["normal_interest", "penalty_interest", "principal"]
        case["transactions"] = [{"id": "r1", "date": "2026-01-02", "type": "repayment", "amount": 100}]

        result = MODULE.calculate(case)["as_of"]

        self.assertEqual(result["due_now"]["principal"], Decimal("1000.00"))
        self.assertEqual(result["due_now"]["penalty_interest"], Decimal("1.00"))
        self.assertNotIn("normal_interest", result["due_now"])

    def test_confirmed_acceleration_moves_future_principal(self) -> None:
        case = {
            "case_name": "提前到期",
            "as_of_date": "2026-01-15",
            "amount_received": 300,
            "scheduled_payments": [
                {"id": "p1", "due_date": "2026-01-01", "components": {"principal": 100}},
                {"id": "p2", "due_date": "2026-02-01", "components": {"principal": 100}},
                {"id": "p3", "due_date": "2026-03-01", "components": {"principal": 100}},
            ],
            "allocation_order": ["principal"],
            "events": [
                {"id": "a1", "type": "acceleration", "date": "2026-01-15", "status": "confirmed"}
            ],
        }

        result = MODULE.calculate(case)["as_of"]

        self.assertEqual(result["amount_due_now"], Decimal("300.00"))
        self.assertEqual(result["future_scheduled_total"], Decimal("0.00"))
        self.assertEqual(result["acceleration_amounts"]["a1"], Decimal("200.00"))

    def test_claim_difference_and_forecast_are_separate(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-02"
        case["forecast_dates"] = ["2026-01-04"]
        case["balance_claims"] = [
            {"date": "2026-01-02", "amount": 1200, "party": "某平台", "status": "claimed"}
        ]

        result = MODULE.calculate(case)

        self.assertEqual(result["as_of"]["amount_due_now"], Decimal("1001.00"))
        self.assertEqual(result["as_of"]["balance_claim"]["difference_from_due_now"], Decimal("199.00"))
        self.assertEqual(result["forecasts"][0]["amount_due_now"], Decimal("1003.00"))

    def test_missing_allocation_order_is_disclosed(self) -> None:
        case = base_case()
        del case["allocation_order"]
        case["transactions"] = [
            {"id": "r1", "date": "2026-01-02", "type": "repayment", "amount": 100, "status": "confirmed"}
        ]

        warnings = MODULE.calculate(case)["as_of"]["warnings"]

        self.assertTrue(any("抵扣顺序缺失" in warning for warning in warnings))

    def test_received_amount_fee_requires_explicit_start_date(self) -> None:
        case = base_case()
        case["fee_rules"][0]["base"] = "amount_received"

        with self.assertRaisesRegex(ValueError, "starts_on is required"):
            MODULE.calculate(case)

    def test_unconfirmed_payment_does_not_reduce_balance(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-01"
        case["transactions"] = [
            {"id": "remembered", "date": "2026-01-01", "type": "repayment", "amount": 500, "status": "claimed"}
        ]

        result = MODULE.calculate(case)["as_of"]

        self.assertEqual(result["amount_due_now"], Decimal("1000.00"))
        self.assertEqual(result["total_repayments_recorded"], Decimal("0.00"))
        self.assertTrue(any("未用于冲减欠款" in warning for warning in result["warnings"]))

    def test_missing_allocation_order_produces_sensitivity_range(self) -> None:
        case = base_case()
        del case["allocation_order"]
        case["scheduled_payments"][0]["components"]["normal_interest"] = 100
        case["transactions"] = [
            {"id": "r1", "date": "2026-01-02", "type": "repayment", "amount": 500, "status": "confirmed"}
        ]

        sensitivity = MODULE.calculate(case)["as_of"]["allocation_sensitivity"]

        self.assertIsNotNone(sensitivity)
        self.assertEqual({item["id"] for item in sensitivity["scenarios"]}, {"principal_first", "fees_first"})
        self.assertLessEqual(sensitivity["amount_due_now_range"]["min"], sensitivity["amount_due_now_range"]["max"])

    def test_only_confirmed_assignment_changes_creditor(self) -> None:
        case = base_case()
        case["entities"] = [
            {"id": "bank", "name": "示例银行", "role": "lender"},
            {"id": "assignee-a", "name": "待定受让方", "role": "assignee"},
            {"id": "assignee-b", "name": "确认受让方", "role": "assignee"},
            {"id": "collector", "name": "催收服务方", "role": "collector"},
        ]
        case["relationships"] = [
            {
                "from": "bank", "to": "borrower", "type": "funded",
                "effective_date": "2026-01-01", "status": "confirmed",
            },
            {
                "id": "possible",
                "from": "bank",
                "to": "assignee-a",
                "type": "assigned",
                "status": "contractual_only",
            },
            {
                "id": "actual",
                "scope": "full",
                "from": "bank",
                "to": "assignee-b",
                "type": "assigned",
                "effective_date": "2026-01-03",
                "status": "confirmed",
            },
            {
                "id": "collection",
                "from": "collector",
                "to": "assignee-b",
                "type": "collects_for",
                "effective_date": "2026-01-04",
                "status": "confirmed",
            },
        ]

        summary = MODULE.calculate(case)["relationship_summary"]

        self.assertEqual(summary["last_confirmed_creditors"], [{"id": "assignee-b", "name": "确认受让方"}])
        self.assertEqual(summary["collectors"], [{"id": "collector", "name": "催收服务方"}])

    def test_public_template_lender_is_candidate_not_confirmed_creditor(self) -> None:
        case = base_case()
        case["entities"] = [
            {"id": "template-lender", "name": "模板贷款人", "role": "lender", "status": "contractual_only"},
            {"id": "possible-assignee", "name": "可能受让方", "role": "assignee", "status": "unknown"},
        ]
        case["relationships"] = [
            {
                "id": "template-funding",
                "from": "template-lender",
                "to": "borrower",
                "type": "funded",
                "status": "contractual_only",
            },
            {
                "id": "possible-transfer",
                "from": "template-lender",
                "to": "possible-assignee",
                "type": "assigned",
                "status": "contractual_only",
            },
        ]

        summary = MODULE.calculate(case)["relationship_summary"]

        self.assertEqual(summary["last_confirmed_creditors"], [])
        self.assertEqual(
            summary["creditor_candidates"],
            [
                {"id": "possible-assignee", "name": "可能受让方"},
                {"id": "template-lender", "name": "模板贷款人"},
            ],
        )

    def test_counter_guarantee_does_not_change_confirmed_creditor(self) -> None:
        case = base_case()
        case["entities"] = [
            {"id": "bank", "name": "示例银行", "role": "lender"},
            {"id": "guarantor", "name": "示例融担", "role": "guarantor"},
            {"id": "platform", "name": "示例平台", "role": "counter_guarantor"},
        ]
        case["relationships"] = [
            {
                "id": "funding",
                "from": "bank",
                "to": "borrower",
                "type": "funded",
                "effective_date": "2026-01-01",
                "status": "confirmed",
            },
            {
                "id": "counter-guarantee",
                "from": "platform",
                "to": "guarantor",
                "type": "counter_guaranteed",
                "effective_date": "2026-01-01",
                "status": "confirmed",
            },
        ]

        summary = MODULE.calculate(case)["relationship_summary"]

        self.assertEqual(summary["last_confirmed_creditors"], [{"id": "bank", "name": "示例银行"}])
        self.assertIn("提供反担保", {item["label"] for item in summary["timeline"]})

    def test_overall_confidence_uses_weakest_material_section(self) -> None:
        case = base_case()
        case["amount_received_evidence"] = {
            "evidence_type": "borrower_recollection",
            "status": "inferred",
            "source": "用户回忆",
        }
        case["scheduled_payments"][0].update({
            "evidence_type": "signed_case_document",
            "source": "已签还款计划",
        })
        case["fee_rules"][0]["evidence_type"] = "signed_case_document"
        case["repayment_history_evidence"] = {
            "evidence_type": "platform_itemized_statement",
            "status": "confirmed",
            "source": "完整平台流水",
        }
        case["repayment_history_complete"] = True

        confidence = MODULE.calculate(case)["evidence_confidence"]

        self.assertEqual(confidence["overall"], {"score": 35, "grade": "D", "label": "仅供估算"})
        self.assertEqual(confidence["weakest_material_sections"], ["amount_received"])

    def test_concise_report_keeps_decision_information(self) -> None:
        case = base_case()
        result = MODULE.calculate(case)

        report = MODULE.markdown_concise(result)

        self.assertIn("重建的当前到期金额", report)
        self.assertIn("可信度", report)
        self.assertIn("当前到期构成", report)
        self.assertIn("最后能够确认的债权人", report)
        self.assertNotIn("方法说明", report)

    def test_cost_analysis_uses_actual_cash_received_and_all_required_payments(self) -> None:
        case = {
            "case_name": "综合成本",
            "as_of_date": "2026-02-01",
            "normal_schedule_complete": True,
            "disbursements": [
                {"date": "2026-01-01", "amount": 1000, "status": "confirmed"}
            ],
            "scheduled_payments": [
                {
                    "due_date": "2027-01-01",
                    "components": {"principal": 1000, "normal_interest": 100, "service_fee": 100},
                    "status": "confirmed",
                }
            ],
            "risk_context": {"nominal_annual_rate_pct": 10, "high_cost_attention_pct": 15},
        }

        costs = MODULE.calculate(case)["cost_analysis"]

        self.assertEqual(costs["normal_financing_cost"], Decimal("200.00"))
        self.assertEqual(costs["all_in_annualized_cost_pct"], Decimal("20.00"))
        self.assertTrue(any("达到15%关注线" in warning for warning in costs["warnings"]))
        self.assertTrue(any("比名义年利率高" in warning for warning in costs["warnings"]))

    def test_overdue_rate_warning_compares_combined_parallel_rules(self) -> None:
        case = base_case()
        case["disbursements"] = [{"date": "2025-01-01", "amount": 1000}]
        case["fee_rules"].append({
            "id": "damages",
            "category": "liquidated_damages",
            "base": "overdue_principal",
            "rate_unit": "daily_pct",
            "rate_value": 0.05,
            "status": "confirmed",
            "source": "担保协议",
        })

        costs = MODULE.calculate(case)["cost_analysis"]

        self.assertEqual(costs["overdue_rate_equivalents"][0]["combined_annualized_rate_pct"], Decimal("54.75"))
        self.assertTrue(any("高于正常融资成本" in warning for warning in costs["warnings"]))

    def test_complete_example_has_high_confidence_and_no_legal_verdict(self) -> None:
        case = complete_ledger_case()

        result = MODULE.calculate(case)

        self.assertEqual(result["evidence_confidence"]["overall"]["grade"], "A")
        self.assertEqual(result["cost_analysis"]["all_in_annualized_cost_pct"], Decimal("44.55"))
        self.assertIsNone(result["cost_analysis"]["legal_limit_conclusion"])

    def test_one_verified_payment_does_not_prove_complete_history(self) -> None:
        case = complete_ledger_case()
        del case["repayment_history_complete"]
        case["transactions"] = case["transactions"][:1]
        result = MODULE.calculate(case)
        self.assertEqual(result["evidence_confidence"]["overall"]["grade"], "E")
        self.assertTrue(any("还款记录完整性" in text for text in result["as_of"]["warnings"]))

    def test_unmatched_early_payment_prevents_high_confidence(self) -> None:
        case = complete_ledger_case()
        case["transactions"].append({"date": "2025-09-20", "amount": 100,
                                     "evidence_type": "bank_transaction", "status": "confirmed", "source": "测试流水"})
        result = MODULE.calculate(case)
        self.assertEqual(result["evidence_confidence"]["overall"]["grade"], "E")
        self.assertIn("unmatched_payments", result["evidence_confidence"]["weakest_material_sections"])

    def test_incomplete_schedule_does_not_publish_all_in_rate(self) -> None:
        case = base_case()
        case["origination_date"] = "2025-01-01"
        case["normal_schedule_complete"] = False
        self.assertIsNone(MODULE.calculate(case)["cost_analysis"]["all_in_annualized_cost_pct"])

    def test_no_new_payment_forecast_ignores_later_transaction(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-02"
        case["forecast_dates"] = ["2026-01-04"]
        case["transactions"] = [{"date": "2026-01-03", "amount": 500}]
        result = MODULE.calculate(case)
        self.assertEqual(result["forecasts"][0]["amount_due_now"], Decimal("1003.00"))
        self.assertEqual(result["forecasts"][0]["total_repayments_recorded"], Decimal("0.00"))

    def test_stale_claim_has_no_same_date_difference(self) -> None:
        case = base_case()
        case["balance_claims"] = [{"date": "2026-01-01", "amount": 1000}]
        result = MODULE.calculate(case)
        self.assertIsNone(result["as_of"]["balance_claim"]["difference_from_total_remaining"])
        self.assertIn("日期不同", MODULE.markdown_concise(result))
        self.assertIn("差额暂不比较", MODULE.markdown_full(result))

    def test_lender_name_alone_does_not_confirm_current_creditor(self) -> None:
        case = base_case()
        case["entities"] = [{"id": "bank", "role": "lender", "name": "示例银行"}]
        self.assertEqual(MODULE.calculate(case)["relationship_summary"]["last_confirmed_creditors"], [])

    def test_partial_compensation_preserves_original_creditor(self) -> None:
        case = base_case()
        case["entities"] = [
            {"id": "bank", "role": "lender", "name": "示例银行"},
            {"id": "guarantor", "role": "guarantor", "name": "示例担保方"},
        ]
        case["relationships"] = [
            {"from": "bank", "to": "borrower", "type": "funded", "status": "confirmed", "effective_date": "2026-01-01"},
            {"from": "guarantor", "to": "bank", "type": "compensated", "status": "confirmed",
             "effective_date": "2026-01-03", "subrogation_confirmed": True, "scope": "partial", "amount": 100},
        ]
        result = MODULE.calculate(case)["relationship_summary"]
        self.assertEqual({item["id"] for item in result["last_confirmed_creditors"]}, {"bank", "guarantor"})
        self.assertTrue(result["ownership_scope_unresolved"])
        self.assertIn("各自余额待核对", MODULE.markdown_concise(MODULE.calculate(case)))

    def test_outstanding_principal_includes_today_due_installment(self) -> None:
        case = base_case()
        case["as_of_date"] = "2026-01-01"
        case["fee_rules"][0].update({"base": "outstanding_principal", "starts_on": "2026-01-01"})
        self.assertEqual(MODULE.calculate(case)["as_of"]["due_now"]["penalty_interest"], Decimal("1.00"))

    def test_non_overlapping_fees_are_not_added_as_parallel_rates(self) -> None:
        case = base_case()
        case["fee_rules"][0]["ends_on"] = "2026-01-02"
        case["fee_rules"].append({**case["fee_rules"][0], "id": "later", "starts_on": "2026-01-03", "ends_on": "2026-01-10"})
        result = MODULE.calculate(case)
        self.assertEqual(result["cost_analysis"]["overdue_rate_equivalents"][0]["combined_annualized_rate_pct"], Decimal("36.50"))
        self.assertFalse(any("存在并行费用" in warning for warning in result["as_of"]["warnings"]))

    def test_rate_equivalent_uses_same_day_count_as_accrual(self) -> None:
        rule = {"rate_unit": "annual_pct", "rate_value": 36, "year_days": 360}
        self.assertEqual(MODULE.annualized_rule_rate(rule), Decimal("36.500"))
        rule = {"rate_unit": "monthly_pct", "rate_value": 3, "month_days": 30}
        self.assertEqual(MODULE.annualized_rule_rate(rule), Decimal("36.500"))

    def test_opening_balance_cannot_duplicate_original_schedule(self) -> None:
        case = base_case()
        case["opening_balance"] = {"date": "2026-01-02", "components": {"principal": 900}}
        with self.assertRaisesRegex(ValueError, "double-count"):
            MODULE.calculate(case)

    def test_invalid_divisor_and_duplicate_transactions_are_rejected(self) -> None:
        case = base_case()
        case["fee_rules"][0]["year_days"] = 0
        with self.assertRaises(ValueError):
            MODULE.calculate(case)
        case = base_case()
        case["transactions"] = [{"id": "duplicate", "date": "2026-01-02", "amount": 10}] * 2
        with self.assertRaisesRegex(ValueError, "duplicate transaction"):
            MODULE.calculate(case)

    def test_irregular_cashflows_with_multiple_sign_changes_have_no_unique_rate(self) -> None:
        cashflows = [(date(2026, 1, 1), Decimal("1000")),
                     (date(2027, 1, 1), Decimal("-2300")),
                     (date(2028, 1, 1), Decimal("1320"))]
        self.assertIsNone(MODULE.xirr(cashflows))


if __name__ == "__main__":
    unittest.main()
