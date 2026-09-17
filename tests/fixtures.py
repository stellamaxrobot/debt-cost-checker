"""Synthetic test data only. No borrower documents or real account records."""


def complete_ledger_case() -> dict:
    def evidence(source: str, kind: str = "signed_case_document") -> dict:
        return {"status": "confirmed", "evidence_type": kind, "source": source}

    return {
        "case_name": "Synthetic installment ledger",
        "currency": "CNY",
        "as_of_date": "2026-01-20",
        "normal_schedule_complete": True,
        "repayment_history_complete": True,
        "repayment_history_evidence": evidence("Synthetic complete payment history", "bank_transaction"),
        "disbursements": [{"id": "d1", "date": "2025-09-10", "amount": 30000,
                           **evidence("Synthetic disbursement", "bank_transaction")}],
        "scheduled_payments": [
            {"id": f"p{index + 1}", "due_date": day,
             "components": {"principal": 5000, "normal_interest": 600 - index * 100, "guarantee_fee": 200},
             **evidence(f"Synthetic schedule row {index + 1}")}
            for index, day in enumerate(["2025-10-10", "2025-11-10", "2025-12-10",
                                         "2026-01-10", "2026-02-10", "2026-03-10"])
        ],
        "transactions": [
            {"id": "r1", "date": "2025-10-10", "type": "repayment", "amount": 5800,
             **evidence("Synthetic payment 1", "bank_transaction")},
            {"id": "r2", "date": "2025-11-18", "type": "repayment", "amount": 3000,
             **evidence("Synthetic payment 2", "bank_transaction")},
        ],
        "allocation_order": ["liquidated_damages", "penalty_interest", "normal_interest", "guarantee_fee", "principal"],
        "allocation_order_evidence": evidence("Synthetic allocation rule"),
        "fee_rules": [
            {"id": "penalty", "category": "penalty_interest", "base": "overdue_principal",
             "rate_unit": "annual_pct", "rate_value": 27, **evidence("Synthetic interest rule")},
            {"id": "damages", "category": "liquidated_damages", "base": "overdue_principal",
             "rate_unit": "daily_pct", "rate_value": 0.03, **evidence("Synthetic damages rule")},
        ],
        "entities": [{"id": "lender", "name": "Synthetic Lender", "role": "lender"}],
        "relationships": [{"from": "lender", "to": "borrower", "type": "funded",
                           "effective_date": "2025-09-10", **evidence("Synthetic funding evidence")}],
        "balance_claims": [{"date": "2026-01-20", "amount": 28000, "party": "Synthetic Platform", "status": "claimed"}],
        "forecast_dates": ["2026-02-20", "2026-04-20"],
        "risk_context": {"nominal_annual_rate_pct": 18},
    }


def prospective_case() -> dict:
    return {
        "case_name": "Synthetic equal-payment simulation",
        "principal": 10000,
        "term_months": 12,
        "annual_interest_rate_pct": 18,
        "guarantee_annual_rate_pct": 6,
        "days_per_period": 30,
        "overdue_snapshots_days": [30, 90, 180],
        "penalty_interest_multiplier": 1.5,
        "overdue_liquidated_daily_rate_pct": 0.0666,
        "simulation_notice": "All values are synthetic test assumptions.",
    }
