#!/usr/bin/env python3
"""Reconstruct an overdue loan from dated obligations, payments and fee rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 28
CENT = Decimal("0.01")
ZERO = Decimal("0")

DEFAULT_ALLOCATION_ORDER = [
    "collection_cost",
    "other_fee",
    "liquidated_damages",
    "penalty_interest",
    "normal_interest",
    "guarantee_fee",
    "insurance_fee",
    "service_fee",
    "principal",
]

PRINCIPAL_FIRST_ORDER = [
    "principal",
    "normal_interest",
    "penalty_interest",
    "liquidated_damages",
    "guarantee_fee",
    "insurance_fee",
    "service_fee",
    "collection_cost",
    "other_fee",
]

CATEGORY_LABELS = {
    "principal": "本金",
    "normal_interest": "正常利息",
    "penalty_interest": "逾期罚息",
    "liquidated_damages": "违约金",
    "guarantee_fee": "担保费",
    "insurance_fee": "保险费",
    "service_fee": "服务费",
    "collection_cost": "催收及实现债权费用",
    "other_fee": "其他费用",
}

RELATIONSHIP_LABELS = {
    "funded": "实际放款",
    "serviced": "平台服务",
    "guaranteed": "提供担保",
    "counter_guaranteed": "提供反担保",
    "insured": "提供保证保险",
    "compensated": "实际代偿",
    "assigned": "债权转让",
    "collects_for": "受托催收",
}

SECTION_LABELS = {
    "amount_received": "实际到账",
    "repayment_history": "还款记录",
    "contractual_schedule": "还款计划",
    "opening_balance": "代偿后起点余额",
    "fee_rules": "计费规则",
    "payment_allocation_order": "还款抵扣顺序",
    "creditor_relationship": "债权关系",
    "balance_events": "影响余额的事件",
    "unmatched_payments": "尚未匹配的还款",
}

STATUS_LABELS = {
    "confirmed": "已确认",
    "claimed": "对方主张",
    "inferred": "推算",
    "assumed": "测试假设",
    "contractual_only": "仅有合同约定，未确认实际发生",
    "unknown": "未知",
}

VALID_BASES = {
    "overdue_principal",
    "overdue_principal_and_interest",
    "outstanding_principal",
    "amount_received",
}
BASE_LABELS = {
    "overdue_principal": "逾期本金",
    "overdue_principal_and_interest": "逾期本金和正常利息",
    "outstanding_principal": "全部未偿本金",
    "amount_received": "实际到账金额",
}
VALID_RATE_UNITS = {"annual_pct", "monthly_pct", "daily_pct"}
NORMAL_COST_CATEGORIES = {
    "principal",
    "normal_interest",
    "guarantee_fee",
    "insurance_fee",
    "service_fee",
    "other_fee",
}

EVIDENCE_WEIGHTS = {
    "bank_transaction": 100,
    "court_finding": 98,
    "signed_case_document": 95,
    "platform_itemized_statement": 88,
    "official_notice": 85,
    "app_screenshot": 68,
    "collector_written_statement": 50,
    "borrower_recollection": 35,
    "public_template": 20,
    "unknown": 10,
}

STATUS_CAPS = {
    "confirmed": 100,
    "inferred": 65,
    "assumed": 55,
    "claimed": 50,
    "contractual_only": 40,
    "unknown": 20,
}

CONFIDENCE_GRADES = [
    (90, "A", "证据充分"),
    (75, "B", "较可靠"),
    (55, "C", "部分推算"),
    (35, "D", "仅供估算"),
    (0, "E", "信息不足"),
]


def dec(value: object) -> Decimal:
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid numeric value: {value}") from exc
    if not result.is_finite():
        raise ValueError("numeric values must be finite")
    return result


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def iso_date(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD: {value}") from exc


def positive_amount(value: object, field: str) -> Decimal:
    amount = dec(value)
    if amount <= ZERO:
        raise ValueError(f"{field} must be positive")
    return amount


def amount_received(data: dict) -> Decimal:
    disbursements = data.get("disbursements", [])
    if disbursements:
        return sum((positive_amount(item["amount"], "disbursements[].amount") for item in disbursements), ZERO)
    if "amount_received" in data:
        return positive_amount(data["amount_received"], "amount_received")
    raise ValueError("provide amount_received or at least one disbursement")


def evidence_score(record: dict | None, default_status: str = "unknown") -> int:
    record = record or {}
    evidence_type = str(record.get("evidence_type", "unknown"))
    status = str(record.get("status", default_status))
    score = EVIDENCE_WEIGHTS.get(evidence_type, EVIDENCE_WEIGHTS["unknown"])
    score = min(score, STATUS_CAPS.get(status, STATUS_CAPS["unknown"]))
    if not record.get("source"):
        score = min(score, 55)
    return score


def confidence_grade(score: int) -> dict:
    for minimum, grade, label in CONFIDENCE_GRADES:
        if score >= minimum:
            return {"score": score, "grade": grade, "label": label}
    raise AssertionError("unreachable confidence score")


def minimum_section_score(records: list[dict], *, empty_evidence: dict | None = None) -> int:
    if records:
        return min(evidence_score(record, str(record.get("status", "unknown"))) for record in records)
    return evidence_score(empty_evidence, "unknown")


def evidence_confidence(data: dict) -> dict:
    target = iso_date(data["as_of_date"], "as_of_date")
    if data.get("disbursements"):
        amount_records = data["disbursements"]
    else:
        amount_records = [data.get("amount_received_evidence") or {
            "evidence_type": "borrower_recollection",
            "status": "inferred",
            "source": "用户填写的实际到账金额",
        }]

    included_schedule = [
        item
        for item in data.get("scheduled_payments", [])
        if item.get("include_in_calculation", item.get("status", "confirmed") in {"confirmed", "assumed"})
    ]
    uses_opening_balance = not included_schedule and bool(data.get("opening_balance"))
    if uses_opening_balance:
        included_schedule = [data["opening_balance"]]
    included_transactions = [
        item
        for item in data.get("transactions", [])
        if item.get("include_in_calculation", item.get("status", "confirmed") in {"confirmed", "assumed"})
        and iso_date(item["date"], "transactions[].date") <= target
    ]
    included_rules = [
        item
        for item in data.get("fee_rules", [])
        if item.get("include_in_calculation", item.get("status", "unknown") in {"confirmed", "assumed"})
    ]
    relationship_records = [
        item
        for item in data.get("relationships", [])
        if item.get("status") == "confirmed" and item.get("type") in {"funded", "assigned", "compensated"}
    ]

    schedule_section = "opening_balance" if uses_opening_balance else "contractual_schedule"
    section_scores = {
        "amount_received": minimum_section_score(amount_records),
        "repayment_history": min(
            minimum_section_score(included_transactions, empty_evidence=data.get("repayment_history_evidence")),
            evidence_score(data.get("repayment_history_evidence"))
            if data.get("repayment_history_complete") is True else 10,
        ),
        schedule_section: minimum_section_score(included_schedule),
        "fee_rules": minimum_section_score(
            included_rules,
            empty_evidence=data.get("fee_rules_evidence"),
        ),
        "creditor_relationship": minimum_section_score(
            relationship_records,
            empty_evidence=data.get("creditor_relationship_evidence"),
        ),
    }
    unresolved_rules = [
        rule for rule in data.get("fee_rules", [])
        if not rule.get("include_in_calculation", rule.get("status", "unknown") in {"confirmed", "assumed"})
    ]
    if unresolved_rules:
        section_scores["fee_rules"] = min(section_scores["fee_rules"], 20)
    if not uses_opening_balance and data.get("normal_schedule_complete") is not True:
        section_scores[schedule_section] = min(section_scores[schedule_section], 10)
    material_sections = ["amount_received", "repayment_history", schedule_section, "fee_rules"]
    events = [event for event in data.get("events", [])
              if event.get("type") == "acceleration" and event.get("status") == "confirmed"
              and event.get("date") and iso_date(event["date"], "events[].date") <= target]
    if events:
        section_scores["balance_events"] = minimum_section_score(events)
        material_sections.append("balance_events")
    if included_transactions:
        allocation_score = evidence_score(data.get("allocation_order_evidence"), "unknown")
        section_scores["payment_allocation_order"] = allocation_score
        material_sections.append("payment_allocation_order")

    overall_score = min(section_scores[name] for name in material_sections)
    weakest = [name for name in material_sections if section_scores[name] == overall_score]
    return {
        "overall": confidence_grade(overall_score),
        "weakest_material_sections": weakest,
        "sections": {name: confidence_grade(score) for name, score in section_scores.items()},
        "method": "Evidence weights are precedence scores, not probabilities. Overall confidence equals the weakest material calculation section.",
    }


def xirr(cashflows: list[tuple[date, Decimal]]) -> Decimal | None:
    if not cashflows or not any(amount > ZERO for _, amount in cashflows) or not any(amount < ZERO for _, amount in cashflows):
        return None
    by_date: defaultdict[date, Decimal] = defaultdict(lambda: ZERO)
    for day, amount in cashflows:
        by_date[day] += amount
    cashflows = [(day, amount) for day, amount in sorted(by_date.items()) if amount != ZERO]
    signs = [amount > ZERO for _, amount in cashflows]
    if sum(left != right for left, right in zip(signs, signs[1:])) != 1:
        return None
    origin = min(day for day, _ in cashflows)

    def npv(rate: float) -> float:
        return sum(
            float(amount) / ((1.0 + rate) ** ((day - origin).days / 365.0))
            for day, amount in cashflows
        )

    low = -0.9
    high = 1.0
    low_value = npv(low)
    high_value = npv(high)
    while low_value * high_value > 0 and high < 10000:
        high = high * 2 + 1
        high_value = npv(high)
    if low_value * high_value > 0:
        return None

    for _ in range(200):
        middle = (low + high) / 2
        middle_value = npv(middle)
        if abs(middle_value) < 1e-10:
            low = high = middle
            break
        if low_value * middle_value <= 0:
            high = middle
        else:
            low = middle
            low_value = middle_value
    return dec(((low + high) / 2) * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def annualized_rule_rate(rule: dict) -> Decimal:
    return daily_rate(rule) * Decimal("36500")


def rule_window(rule: dict) -> tuple[date, date]:
    start = iso_date(rule["starts_on"], "starts_on") if rule.get("starts_on") else date.min
    end = iso_date(rule["ends_on"], "ends_on") if rule.get("ends_on") else date.max
    return start, end


def peak_overlapping_rate(rules: list[dict]) -> Decimal:
    boundaries = {rule_window(rule)[0] for rule in rules}
    return max((sum((annualized_rule_rate(rule) for rule in rules
                     if rule_window(rule)[0] <= day <= rule_window(rule)[1]), ZERO)
                for day in boundaries), default=ZERO)


def cost_analysis(data: dict) -> dict:
    received = amount_received(data)
    schedule = normalized_schedule(data, include_opening=False)
    warnings = []
    cashflows: list[tuple[date, Decimal]] = []

    if data.get("disbursements"):
        for item in data["disbursements"]:
            cashflows.append((iso_date(item["date"], "disbursements[].date"), dec(item["amount"])))
    elif data.get("origination_date"):
        cashflows.append((iso_date(data["origination_date"], "origination_date"), received))

    normal_repayment = ZERO
    for row in schedule:
        if not row["included"]:
            continue
        amount = sum(
            (value for category, value in row["components"].items() if category in NORMAL_COST_CATEGORIES),
            ZERO,
        )
        normal_repayment += amount
        if cashflows and amount > ZERO:
            cashflows.append((row["due_date"], -amount))

    complete_schedule = (data.get("normal_schedule_complete") is True and bool(schedule)
                         and all(row["included"] for row in schedule))
    all_in_rate = xirr(cashflows) if cashflows and complete_schedule else None
    context = data.get("risk_context") or {}
    nominal = dec(context["nominal_annual_rate_pct"]) if context.get("nominal_annual_rate_pct") is not None else None
    attention = dec(context["high_cost_attention_pct"]) if context.get("high_cost_attention_pct") is not None else None

    if attention is not None and not context.get("high_cost_attention_source"):
        warnings.append("综合融资成本关注线没有注明来源，只能作为用户设置的提示线。")

    if all_in_rate is not None and attention is not None and all_in_rate >= attention:
        warnings.append(
            f"正常履约综合融资成本年化{all_in_rate}%达到{attention}%关注线；关注线用于提示核对，不代表违法认定。"
        )
    if all_in_rate is not None and nominal is not None and all_in_rate - nominal >= Decimal("5"):
        warnings.append(
            f"按全部正常还款现金流计算的综合成本比名义年利率高{money(all_in_rate - nominal)}个百分点；"
            "请核对附加费用和还款计划。"
        )

    overdue_by_base: defaultdict[str, list[dict]] = defaultdict(list)
    for rule in data.get("fee_rules", []):
        include = rule.get("include_in_calculation", rule.get("status", "unknown") in {"confirmed", "assumed"})
        if include and rule.get("base") in {"overdue_principal", "overdue_principal_and_interest"}:
            overdue_by_base[rule["base"]].append(rule)

    overdue_rates = []
    comparison_rate = all_in_rate if all_in_rate is not None else nominal
    overdue_attention = dec(context["overdue_cost_attention_pct"]) if context.get("overdue_cost_attention_pct") is not None else None
    if overdue_attention is not None and not context.get("overdue_cost_attention_source"):
        warnings.append("逾期费用关注线没有注明来源，只能作为用户设置的提示线。")
    for base, rules in overdue_by_base.items():
        annualized = money(peak_overlapping_rate(rules))
        overdue_rates.append({"base": base, "combined_annualized_rate_pct": annualized,
                              "method": "maximum overlapping simple annualized rates"})
        base_label = BASE_LABELS.get(base, base)
        if overdue_attention is not None and annualized >= overdue_attention:
            warnings.append(
                f"以{base_label}为基数并行计算的逾期费用折算年化约{annualized}%，达到{overdue_attention}%关注线。"
            )
        elif comparison_rate is not None and annualized > comparison_rate:
            warnings.append(
                f"以{base_label}为基数并行计算的逾期费用折算年化约{annualized}%，高于正常融资成本，需核对是否并行及计费基数。"
            )

    if data.get("case_scope") == "post_compensation_recovery" and not schedule:
        warnings.append("当前是代偿后追偿账本，缺少原始逐期还款计划，未重算正常履约综合年化成本。")
    elif not complete_schedule:
        warnings.append("正常还款计划完整性尚未确认，暂不计算完整融资成本与综合年化。")
    elif cashflows and all_in_rate is None:
        warnings.append("正常履约现金流无法得到唯一综合年化成本，请核对放款日期和还款计划。")
    elif not cashflows:
        warnings.append("缺少放款日期，暂时无法计算正常履约综合年化成本。")

    return {
        "amount_received": money(received),
        "normal_repayment_total": money(normal_repayment) if complete_schedule else None,
        "normal_financing_cost": money(normal_repayment - received) if complete_schedule else None,
        "known_scheduled_repayment_total": money(normal_repayment),
        "nominal_annual_rate_pct": money(nominal) if nominal is not None else None,
        "all_in_annualized_cost_pct": all_in_rate,
        "overdue_rate_equivalents": overdue_rates,
        "comparison_context": context,
        "warnings": list(dict.fromkeys(warnings)),
        "legal_limit_conclusion": None,
    }


def validate(data: dict) -> None:
    for field in ("case_name", "as_of_date"):
        if field not in data:
            raise ValueError(f"missing required field: {field}")
    target = iso_date(data["as_of_date"], "as_of_date")
    if data.get("currency", "CNY") != "CNY":
        raise ValueError("this version supports CNY only")
    if data.get("loans"):
        raise ValueError("calculate each loan separately; a multi-loan allocation ledger is not supported")
    amount_received(data)
    if not data.get("scheduled_payments") and not data.get("opening_balance"):
        raise ValueError("provide scheduled_payments or opening_balance")

    seen_ids: set[str] = set()
    for index, row in enumerate(data.get("scheduled_payments", [])):
        row_id = str(row.get("id", f"schedule-{index + 1}"))
        if row_id in seen_ids:
            raise ValueError(f"duplicate scheduled payment id: {row_id}")
        seen_ids.add(row_id)
        iso_date(row.get("due_date"), f"scheduled_payments[{index}].due_date")
        components = row.get("components") or {}
        if not components:
            raise ValueError(f"scheduled_payments[{index}].components cannot be empty")
        for category, value in components.items():
            if category not in CATEGORY_LABELS:
                raise ValueError(f"unsupported component category: {category}")
            if dec(value) < ZERO:
                raise ValueError(f"scheduled payment component cannot be negative: {row_id}.{category}")

    opening = data.get("opening_balance")
    if opening:
        opening_date = iso_date(opening.get("date"), "opening_balance.date")
        if data.get("scheduled_payments"):
            raise ValueError("opening_balance and scheduled_payments cannot be combined; this would double-count debt")
        if opening_date > target:
            raise ValueError("opening_balance.date cannot be later than as_of_date")
        components = opening.get("components") or {}
        if not components:
            raise ValueError("opening_balance.components cannot be empty")
        for category, value in components.items():
            if category not in CATEGORY_LABELS:
                raise ValueError(f"unsupported opening balance category: {category}")
            if dec(value) < ZERO:
                raise ValueError(f"opening balance component cannot be negative: {category}")

    transaction_ids = set()
    for index, transaction in enumerate(data.get("transactions", [])):
        transaction_date = iso_date(transaction.get("date"), f"transactions[{index}].date")
        if opening and transaction_date <= opening_date:
            raise ValueError("transactions must follow the opening balance date; earlier payments are already reflected")
        if transaction.get("id") is not None:
            if transaction["id"] in transaction_ids:
                raise ValueError(f"duplicate transaction id: {transaction['id']}")
            transaction_ids.add(transaction["id"])
        if transaction.get("type", "repayment") not in {"repayment", "waiver"}:
            raise ValueError(f"unsupported transaction type: {transaction.get('type')}")
        positive_amount(transaction.get("amount"), f"transactions[{index}].amount")
        category = transaction.get("category")
        if category is not None and category not in CATEGORY_LABELS:
            raise ValueError(f"unsupported transaction category: {category}")

    for index, rule in enumerate(data.get("fee_rules", [])):
        if rule.get("base") not in VALID_BASES:
            raise ValueError(f"unsupported fee base in fee_rules[{index}]: {rule.get('base')}")
        if rule.get("rate_unit") not in VALID_RATE_UNITS:
            raise ValueError(f"unsupported rate unit in fee_rules[{index}]: {rule.get('rate_unit')}")
        positive_amount(rule.get("rate_value"), f"fee_rules[{index}].rate_value")
        for field, default in (("year_days", 365), ("month_days", 30)):
            positive_amount(rule.get(field, default), f"fee_rules[{index}].{field}")
        wait = dec(rule.get("start_after_days", 0))
        if wait < ZERO or wait != wait.to_integral_value():
            raise ValueError("start_after_days must be a non-negative integer")
        category = rule.get("category")
        if category not in CATEGORY_LABELS or category == "principal":
            raise ValueError(f"unsupported fee category in fee_rules[{index}]: {category}")
        if rule.get("starts_on") is not None:
            iso_date(rule["starts_on"], f"fee_rules[{index}].starts_on")
        if rule.get("ends_on") is not None:
            iso_date(rule["ends_on"], f"fee_rules[{index}].ends_on")
        if rule.get("base") in {"amount_received", "outstanding_principal"} and not rule.get("starts_on"):
            raise ValueError(f"fee_rules[{index}].starts_on is required for base={rule.get('base')}")
        if rule_window(rule)[0] > rule_window(rule)[1]:
            raise ValueError("fee rule ends_on must not precede starts_on")
        if opening and rule.get("starts_on") and rule_window(rule)[0] < opening_date:
            raise ValueError("fee rule starts_on must not precede opening_balance.date")

    order = data.get("allocation_order") or []
    if len(order) != len(set(order)) or any(category not in CATEGORY_LABELS for category in order):
        raise ValueError("allocation_order must contain distinct supported categories")

    for index, forecast in enumerate(data.get("forecast_dates", [])):
        forecast_date = iso_date(forecast, f"forecast_dates[{index}]")
        if forecast_date <= target:
            raise ValueError("forecast_dates must be later than as_of_date")


def normalized_schedule(data: dict, *, include_opening: bool = True) -> list[dict]:
    rows = []
    for index, item in enumerate(data.get("scheduled_payments", [])):
        status = item.get("status", "confirmed")
        rows.append({
            "id": str(item.get("id", f"schedule-{index + 1}")),
            "due_date": iso_date(item["due_date"], "scheduled_payments[].due_date"),
            "components": {key: dec(value) for key, value in item["components"].items()},
            "status": status,
            "included": item.get("include_in_calculation", status in {"confirmed", "assumed"}),
            "source": item.get("source"),
        })
    if include_opening and data.get("opening_balance"):
        item = data["opening_balance"]
        status = item.get("status", "confirmed")
        rows.append({
            "id": str(item.get("id", "opening-balance")),
            "due_date": iso_date(item["date"], "opening_balance.date"),
            "components": {key: dec(value) for key, value in item["components"].items()},
            "status": status,
            "included": item.get("include_in_calculation", status in {"confirmed", "assumed"}),
            "source": item.get("source"),
            "opening_balance": True,
        })
    return sorted(rows, key=lambda row: (row["due_date"], row["id"]))


def daily_rate(rule: dict) -> Decimal:
    rate = dec(rule["rate_value"]) / Decimal("100")
    if rule["rate_unit"] == "annual_pct":
        return rate / dec(rule.get("year_days", 365))
    if rule["rate_unit"] == "monthly_pct":
        return rate / dec(rule.get("month_days", 30))
    return rate


def add_obligation(
    obligations: list[dict],
    *,
    obligation_id: str,
    due_date: date,
    category: str,
    amount: Decimal,
    label: str,
    status: str,
    source: object = None,
    generated_by: str | None = None,
) -> None:
    if amount <= ZERO:
        return
    obligations.append({
        "id": obligation_id,
        "due_date": due_date,
        "category": category,
        "label": label,
        "original": amount,
        "remaining": amount,
        "status": status,
        "source": source,
        "generated_by": generated_by,
    })


def remaining_by_category(obligations: list[dict], categories: set[str] | None = None) -> Decimal:
    return sum(
        (
            item["remaining"]
            for item in obligations
            if item["remaining"] > ZERO and (categories is None or item["category"] in categories)
        ),
        ZERO,
    )


def future_principal(schedule: list[dict], current: date) -> Decimal:
    return sum(
        (
            row["components"].get("principal", ZERO)
            for row in schedule
            if row["included"] and row["due_date"] > current
        ),
        ZERO,
    )


def eligible_fee_base(rule: dict, obligations: list[dict], schedule: list[dict], current: date, received: Decimal) -> Decimal:
    base = rule["base"]
    wait_days = int(rule.get("start_after_days", 0))

    def eligible(item: dict) -> bool:
        return item["remaining"] > ZERO and (current - item["due_date"]).days > wait_days

    if base == "overdue_principal":
        return sum((item["remaining"] for item in obligations if item["category"] == "principal" and eligible(item)), ZERO)
    if base == "overdue_principal_and_interest":
        return sum(
            (
                item["remaining"]
                for item in obligations
                if item["category"] in {"principal", "normal_interest"} and eligible(item)
            ),
            ZERO,
        )
    if base == "outstanding_principal":
        due_today = sum((row["components"].get("principal", ZERO) for row in schedule
                         if row["included"] and row["due_date"] == current
                         and not row.get("opening_balance")), ZERO)
        return remaining_by_category(obligations, {"principal"}) + future_principal(schedule, current) + due_today
    return received


def apply_transaction(
    transaction: dict,
    obligations: list[dict],
    allocation_order: list[str],
) -> dict:
    remaining = dec(transaction["amount"])
    selected_category = transaction.get("category")
    order = {category: position for position, category in enumerate(allocation_order)}
    candidates = [
        item
        for item in obligations
        if item["remaining"] > ZERO and (selected_category is None or item["category"] == selected_category)
    ]
    candidates.sort(key=lambda item: (order.get(item["category"], len(order)), item["due_date"], item["id"]))

    allocations = []
    for obligation in candidates:
        if remaining <= ZERO:
            break
        applied = min(remaining, obligation["remaining"])
        obligation["remaining"] -= applied
        remaining -= applied
        allocations.append({
            "obligation_id": obligation["id"],
            "category": obligation["category"],
            "amount": applied,
        })

    return {
        "id": str(transaction.get("id", "transaction")),
        "date": iso_date(transaction["date"], "transaction.date"),
        "type": transaction.get("type", "repayment"),
        "amount": dec(transaction["amount"]),
        "allocations": allocations,
        "unapplied": remaining,
        "status": transaction.get("status", "confirmed"),
        "source": transaction.get("source"),
    }


def apply_acceleration(event: dict, schedule: list[dict], obligations: list[dict], current: date) -> Decimal:
    component_names = {"principal"}
    if event.get("include_future_interest", False):
        component_names.add("normal_interest")
    if event.get("include_future_fees", False):
        component_names.update({"guarantee_fee", "insurance_fee", "service_fee", "other_fee"})

    accelerated = ZERO
    for row in schedule:
        if not row["included"] or row["due_date"] <= current:
            continue
        for category in component_names:
            amount = row["components"].get(category, ZERO)
            if amount <= ZERO:
                continue
            add_obligation(
                obligations,
                obligation_id=f"{event.get('id', 'acceleration')}:{row['id']}:{category}",
                due_date=current,
                category=category,
                amount=amount,
                label=f"提前到期的{CATEGORY_LABELS[category]}",
                status="confirmed",
                source=event.get("source"),
                generated_by=str(event.get("id", "acceleration")),
            )
            accelerated += amount
            row["components"][category] = ZERO
    return accelerated


def breakdown(obligations: list[dict]) -> dict[str, Decimal]:
    result = {category: ZERO for category in CATEGORY_LABELS}
    for item in obligations:
        if item["remaining"] > ZERO:
            result[item["category"]] += item["remaining"]
    return {key: money(value) for key, value in result.items() if value > ZERO}


def summarize_open_obligations(obligations: list[dict]) -> list[dict]:
    grouped: dict[tuple, dict] = {}
    for item in obligations:
        if item["remaining"] <= ZERO:
            continue
        source_key = json.dumps(item.get("source"), ensure_ascii=False, sort_keys=True, default=str)
        key = (
            item["category"],
            item["label"],
            item["status"],
            source_key,
            item.get("generated_by"),
        )
        if key not in grouped:
            grouped[key] = {
                "category": item["category"],
                "label": item["label"],
                "status": item["status"],
                "source": item.get("source"),
                "generated_by": item.get("generated_by"),
                "amount": ZERO,
                "item_count": 0,
                "first_due_date": item["due_date"],
                "last_due_date": item["due_date"],
            }
        summary = grouped[key]
        summary["amount"] += item["remaining"]
        summary["item_count"] += 1
        summary["first_due_date"] = min(summary["first_due_date"], item["due_date"])
        summary["last_due_date"] = max(summary["last_due_date"], item["due_date"])

    result = list(grouped.values())
    for item in result:
        item["amount"] = money(item["amount"])
    return sorted(result, key=lambda item: (item["first_due_date"], item["category"], item["label"]))


def future_breakdown(schedule: list[dict], target: date) -> dict[str, Decimal]:
    result: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    for row in schedule:
        if not row["included"] or row["due_date"] <= target:
            continue
        for category, value in row["components"].items():
            result[category] += value
    return {key: money(value) for key, value in result.items() if value > ZERO}


def latest_claim(data: dict, target: date) -> dict | None:
    candidates = []
    for item in data.get("balance_claims", []):
        claim_date = iso_date(item["date"], "balance_claims[].date")
        if claim_date <= target:
            candidates.append((claim_date, item))
    if not candidates:
        return None
    claim_date, item = max(candidates, key=lambda pair: pair[0])
    return {
        "date": claim_date,
        "amount": dec(item["amount"]),
        "party": item.get("party", "未注明主张方"),
        "status": item.get("status", "claimed"),
        "source": item.get("source"),
    }


def relationship_summary(data: dict, target: date) -> dict:
    entities = {str(item.get("id")): item for item in data.get("entities", []) if item.get("id") is not None}
    creditors: set[str] = set()
    creditor_candidates = {
        entity_id
        for entity_id, item in entities.items()
        if item.get("role") in {"lender", "assignee", "compensating_party"}
    }
    collectors: set[str] = set()
    compensating_parties: set[str] = set()
    timeline = []
    warnings = []
    ownership_scope_unresolved = False

    def name(entity_id: str) -> str:
        entity = entities.get(entity_id)
        return str(entity.get("name")) if entity and entity.get("name") else entity_id

    sortable = []
    for index, relationship in enumerate(data.get("relationships", [])):
        item = deepcopy(relationship)
        item["id"] = str(item.get("id", f"relationship-{index + 1}"))
        effective = iso_date(item["effective_date"], "relationships[].effective_date") if item.get("effective_date") else None
        item["effective_date_value"] = effective
        sortable.append(item)

    sortable.sort(key=lambda item: (item["effective_date_value"] or date.max, item["id"]))
    for item in sortable:
        from_id = str(item.get("from", "unknown"))
        to_id = str(item.get("to", "unknown"))
        status = item.get("status", "unknown")
        relationship_type = item.get("type", "unknown")
        effective = item["effective_date_value"]
        applies_by_date = effective is not None and effective <= target

        for entity_id in (from_id, to_id):
            if entity_id != "unknown" and entity_id not in entities and entity_id != "borrower":
                warnings.append(f"关系“{item['id']}”引用了未定义参与方：{entity_id}。")

        timeline.append({
            "id": item["id"],
            "effective_date": effective,
            "type": relationship_type,
            "label": RELATIONSHIP_LABELS.get(relationship_type, relationship_type),
            "from": from_id,
            "from_name": name(from_id),
            "to": to_id,
            "to_name": name(to_id),
            "amount": dec(item["amount"]) if item.get("amount") is not None else None,
            "status": status,
            "source": item.get("source"),
        })

        if status != "confirmed":
            if relationship_type == "funded":
                creditor_candidates.add(from_id)
            elif relationship_type == "assigned":
                creditor_candidates.add(to_id)
            elif relationship_type == "compensated" and item.get("subrogation_confirmed", False):
                creditor_candidates.add(from_id)
            continue
        if not effective:
            warnings.append(f"已确认关系“{item['id']}”缺少生效日期，未用于判断当前债权人。")
            continue
        if effective > target:
            continue

        if relationship_type == "funded":
            creditors.add(from_id)
        elif relationship_type == "assigned" and applies_by_date:
            if from_id not in creditors:
                warnings.append(f"债权转让“{item['id']}”的转让方不是此前已确认债权人，需要补齐前序关系。")
            if item.get("scope", "unknown") == "full":
                creditors.discard(from_id)
            else:
                ownership_scope_unresolved = True
                warnings.append(f"债权转让“{item['id']}”未确认覆盖整笔余额，保留原债权人，双方金额范围待核对。")
            creditors.add(to_id)
        elif relationship_type == "compensated" and applies_by_date:
            compensating_parties.add(from_id)
            if item.get("subrogation_confirmed", False):
                if item.get("scope", "unknown") == "full":
                    creditors.discard(to_id)
                else:
                    ownership_scope_unresolved = True
                    warnings.append(f"代偿“{item['id']}”未确认覆盖整笔余额，保留原债权人，追偿金额范围待核对。")
                creditors.add(from_id)
            else:
                warnings.append(f"代偿“{item['id']}”已记录，但追偿权转移证据未确认，未据此变更债权人。")
        elif relationship_type == "collects_for" and applies_by_date:
            collectors.add(from_id)

    return {
        "last_confirmed_creditors": [
            {"id": entity_id, "name": name(entity_id)} for entity_id in sorted(creditors)
        ],
        "creditor_candidates": [
            {"id": entity_id, "name": name(entity_id)}
            for entity_id in sorted(creditor_candidates - creditors)
        ],
        "collectors": [{"id": entity_id, "name": name(entity_id)} for entity_id in sorted(collectors)],
        "compensating_parties": [
            {"id": entity_id, "name": name(entity_id)} for entity_id in sorted(compensating_parties)
        ],
        "ownership_scope_unresolved": ownership_scope_unresolved,
        "timeline": timeline,
        "warnings": list(dict.fromkeys(warnings)),
    }


def run_to_date(data: dict, target: date) -> dict:
    schedule = normalized_schedule(data)
    received = amount_received(data)
    obligations: list[dict] = []
    allocations = []
    warnings = []
    fee_totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    acceleration_totals: defaultdict[str, Decimal] = defaultdict(lambda: ZERO)
    if data.get("repayment_history_complete") is not True:
        warnings.append("还款记录完整性尚未确认：未提供的还款没有自动记为零，当前金额仅为现有记录下的测算。")
    elif not data.get("repayment_history_evidence", {}).get("source"):
        warnings.append("还款记录虽标注完整，但缺少完整性核对的出处，可信度仍受限制。")
    if not data.get("opening_balance") and data.get("normal_schedule_complete") is not True:
        warnings.append("还款计划可能缺期，当前到期和剩余总额只覆盖已提供的项目。")

    allocation_order = data.get("allocation_order") or DEFAULT_ALLOCATION_ORDER
    if not data.get("allocation_order") and data.get("transactions"):
        warnings.append("还款抵扣顺序缺失：当前使用演示顺序，结果属于推算而非已确认余额。")

    contract_schedule = [row for row in schedule if not row.get("opening_balance")]
    scheduled_principal = sum(
        (row["components"].get("principal", ZERO) for row in contract_schedule if row["included"]),
        ZERO,
    )
    if contract_schedule and money(scheduled_principal) != money(received):
        warnings.append(
            f"还款计划中的本金合计{money(scheduled_principal)}元与实际到账{money(received)}元不一致；"
            "请核对合同本金、放款前扣费或缺失的分期记录。"
        )
    for row in schedule:
        if not row["included"]:
            warnings.append(f"还款计划“{row['id']}”状态为{row['status']}，未计入金额。")

    rules = []
    for index, raw_rule in enumerate(data.get("fee_rules", [])):
        rule = deepcopy(raw_rule)
        rule["id"] = str(rule.get("id", f"fee-rule-{index + 1}"))
        rule["status"] = rule.get("status", "unknown")
        rule["starts_on_date"] = iso_date(rule["starts_on"], "fee_rule.starts_on") if rule.get("starts_on") else None
        rule["ends_on_date"] = iso_date(rule["ends_on"], "fee_rule.ends_on") if rule.get("ends_on") else None
        include = rule.get("include_in_calculation", rule["status"] in {"confirmed", "assumed"})
        if include:
            rules.append(rule)
        else:
            status_label = STATUS_LABELS.get(rule["status"], rule["status"])
            warnings.append(f"费用规则“{rule.get('label', rule['id'])}”未计入：{status_label}。")
        if not rule.get("source"):
            warnings.append(f"费用规则“{rule.get('label', rule['id'])}”缺少协议出处。")

    active_by_base: defaultdict[str, list[dict]] = defaultdict(list)
    for rule in rules:
        active_by_base[rule["base"]].append(rule)
    for base, same_base_rules in active_by_base.items():
        overlaps = [rule for index, rule in enumerate(same_base_rules)
                    if any(index != other_index and max(rule_window(rule)[0], rule_window(other)[0])
                           <= min(rule_window(rule)[1], rule_window(other)[1])
                           for other_index, other in enumerate(same_base_rules))]
        if overlaps:
            labels = [rule.get("label", rule["id"]) for rule in overlaps]
            warnings.append(
                f"同一计费基数“{BASE_LABELS.get(base, base)}”存在并行费用："
                f"{'、'.join(labels)}；需要核对是否允许同时收取。"
            )

    schedules_by_date: defaultdict[date, list[dict]] = defaultdict(list)
    for row in schedule:
        schedules_by_date[row["due_date"]].append(row)

    transactions_by_date: defaultdict[date, list[dict]] = defaultdict(list)
    for index, item in enumerate(data.get("transactions", [])):
        item = deepcopy(item)
        item["id"] = str(item.get("id", f"transaction-{index + 1}"))
        transaction_date = iso_date(item["date"], "transactions[].date")
        status = item.get("status", "confirmed")
        include = item.get("include_in_calculation", status in {"confirmed", "assumed"})
        if transaction_date <= target and include:
            transactions_by_date[transaction_date].append(item)
        elif transaction_date <= target:
            warnings.append(f"交易“{item['id']}”状态为{status}，未用于冲减欠款。")

    events_by_date: defaultdict[date, list[dict]] = defaultdict(list)
    for index, item in enumerate(data.get("events", [])):
        if "date" not in item:
            warnings.append(f"事件“{item.get('id', index + 1)}”没有日期，未进入金额计算。")
            continue
        event_date = iso_date(item["date"], "events[].date")
        if event_date <= target:
            event = deepcopy(item)
            event["id"] = str(event.get("id", f"event-{index + 1}"))
            events_by_date[event_date].append(event)

    dates = [row["due_date"] for row in schedule if row["included"] and row["due_date"] <= target]
    dates += list(transactions_by_date)
    dates += list(events_by_date)
    dates += [rule["starts_on_date"] for rule in rules if rule["starts_on_date"] and rule["starts_on_date"] <= target]
    if not dates:
        start = target
    else:
        start = min(dates)

    current = start
    while current <= target:
        for rule in rules:
            if rule["starts_on_date"] and current < rule["starts_on_date"]:
                continue
            if rule["ends_on_date"] and current > rule["ends_on_date"]:
                continue
            base = eligible_fee_base(rule, obligations, schedule, current, received)
            accrued = base * daily_rate(rule)
            if accrued > ZERO:
                category = rule["category"]
                add_obligation(
                    obligations,
                    obligation_id=f"{rule['id']}:{current.isoformat()}",
                    due_date=current,
                    category=category,
                    amount=accrued,
                    label=rule.get("label", CATEGORY_LABELS[category]),
                    status=rule["status"],
                    source=rule.get("source"),
                    generated_by=rule["id"],
                )
                fee_totals[rule["id"]] += accrued

        for row in schedules_by_date.get(current, []):
            if not row["included"]:
                continue
            for category, component_amount in row["components"].items():
                add_obligation(
                    obligations,
                    obligation_id=f"{row['id']}:{category}",
                    due_date=current,
                    category=category,
                    amount=component_amount,
                    label=CATEGORY_LABELS[category],
                    status=row["status"],
                    source=row["source"],
                )

        for event in events_by_date.get(current, []):
            event_type = event.get("type")
            if event_type == "acceleration" and event.get("status") == "confirmed":
                acceleration_totals[event["id"]] += apply_acceleration(event, schedule, obligations, current)
            elif event_type == "acceleration":
                status = event.get("status", "unknown")
                warnings.append(f"提前到期事件“{event['id']}”{STATUS_LABELS.get(status, status)}，未计入金额。")

        for transaction in transactions_by_date.get(current, []):
            allocation = apply_transaction(transaction, obligations, allocation_order)
            allocations.append(allocation)
            if allocation["unapplied"] > ZERO:
                warnings.append(
                    f"{current.isoformat()}的{transaction.get('type', 'repayment')}有"
                    f"{money(allocation['unapplied'])}元未能匹配到当日已到期项目；请核对是否属于提前还款或记录缺失。"
                )
        current += timedelta(days=1)

    due = breakdown(obligations)
    future = future_breakdown(schedule, target)
    due_total = money(sum(due.values(), ZERO))
    future_total = money(sum(future.values(), ZERO))
    remaining_total = money(due_total + future_total)
    included_transactions = [item for items in transactions_by_date.values() for item in items]
    total_paid = money(sum((dec(item["amount"]) for item in included_transactions if item.get("type", "repayment") == "repayment"), ZERO))
    total_waived = money(sum((dec(item["amount"]) for item in included_transactions if item.get("type") == "waiver"), ZERO))
    claim = latest_claim(data, target)

    claim_result = None
    if claim and claim["date"] == target:
        claim_result = {
            **claim,
            "comparable_on_target_date": True,
            "difference_from_due_now": money(claim["amount"] - due_total),
            "difference_from_total_remaining": money(claim["amount"] - remaining_total),
        }
        closest_difference = min(abs(claim["amount"] - due_total), abs(claim["amount"] - remaining_total))
        if closest_difference <= Decimal("1.00"):
            warnings.append("对方主张金额与重建结果相差不超过1元，优先核对起止日是否计入及逐日分位取整口径。")
        elif claim["amount"] != due_total and claim["amount"] != remaining_total:
            warnings.append("对方主张金额与重建的到期金额、剩余合同金额均不一致，差额需要逐项对账。")
    elif claim:
        claim_result = {**claim, "comparable_on_target_date": False,
                        "difference_from_due_now": None, "difference_from_total_remaining": None}
        warnings.append(f"对方主张金额的日期为{claim['date']}，与本次测算日不同，未直接计算差额。")

    return {
        "target_date": target,
        "amount_received": money(received),
        "total_repayments_recorded": total_paid,
        "total_waivers_recorded": total_waived,
        "remaining_principal": money(due.get("principal", ZERO) + future.get("principal", ZERO)),
        "due_now": due,
        "amount_due_now": due_total,
        "future_schedule": future,
        "future_scheduled_total": future_total,
        "total_remaining_before_unknown_costs": remaining_total,
        "fee_accruals": {rule_id: money(value) for rule_id, value in fee_totals.items()},
        "acceleration_amounts": {event_id: money(value) for event_id, value in acceleration_totals.items()},
        "open_obligations": summarize_open_obligations(obligations),
        "payment_allocations": allocations,
        "balance_claim": claim_result,
        "warnings": list(dict.fromkeys(warnings)),
    }


def serialize(value: object) -> str:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def allocation_sensitivity(data: dict, target: date) -> dict | None:
    if data.get("allocation_order") or not data.get("transactions"):
        return None

    scenarios = []
    for scenario_id, label, order in (
        ("principal_first", "本金优先", PRINCIPAL_FIRST_ORDER),
        ("fees_first", "息费优先", DEFAULT_ALLOCATION_ORDER),
    ):
        scenario_data = deepcopy(data)
        scenario_data["allocation_order"] = order
        result = run_to_date(scenario_data, target)
        scenarios.append({
            "id": scenario_id,
            "label": label,
            "amount_due_now": result["amount_due_now"],
            "remaining_principal": result["remaining_principal"],
            "total_remaining_before_unknown_costs": result["total_remaining_before_unknown_costs"],
        })

    due_values = [item["amount_due_now"] for item in scenarios]
    total_values = [item["total_remaining_before_unknown_costs"] for item in scenarios]
    return {
        "reason": "合同或入账记录未确认还款抵扣顺序；两种情景仅用于观察该缺口对余额的影响。",
        "amount_due_now_range": {"min": min(due_values), "max": max(due_values)},
        "total_remaining_range": {"min": min(total_values), "max": max(total_values)},
        "scenarios": scenarios,
    }


def calculate(data: dict) -> dict:
    validate(data)
    as_of = iso_date(data["as_of_date"], "as_of_date")
    current = run_to_date(data, as_of)
    current["allocation_sensitivity"] = allocation_sensitivity(data, as_of)
    confidence = evidence_confidence(data)
    if any(item["unapplied"] > ZERO for item in current["payment_allocations"]):
        confidence["sections"]["unmatched_payments"] = confidence_grade(10)
        if confidence["overall"]["score"] > 10:
            confidence["overall"] = confidence_grade(10)
            confidence["weakest_material_sections"] = ["unmatched_payments"]
        elif confidence["overall"]["score"] == 10:
            confidence["weakest_material_sections"].append("unmatched_payments")
    forecasts = []
    forecast_data = deepcopy(data)
    forecast_data["transactions"] = [item for item in data.get("transactions", [])
                                     if iso_date(item["date"], "transactions[].date") <= as_of]
    forecast_data["balance_claims"] = []
    for value in data.get("forecast_dates", []):
        forecast_date = iso_date(value, "forecast_dates[]")
        forecast = run_to_date(forecast_data, forecast_date)
        forecast["allocation_sensitivity"] = allocation_sensitivity(forecast_data, forecast_date)
        forecasts.append(forecast)
    return {
        "case_name": data["case_name"],
        "currency": data.get("currency", "CNY"),
        "status": "document-based reconstruction",
        "as_of": current,
        "forecasts": forecasts,
        "entities": data.get("entities", []),
        "relationships": data.get("relationships", []),
        "events": data.get("events", []),
        "relationship_summary": relationship_summary(data, as_of),
        "evidence_confidence": confidence,
        "cost_analysis": cost_analysis(data),
        "unknown_items": data.get("unknown_items", []),
        "method_notes": [
            "到期日当天还款不产生逾期费用。逾期后，每天先按当日开始时的逾期余额计费，再处理当天还款。",
            "只有状态为confirmed或明确设为include_in_calculation的费用规则进入金额。",
            "只有confirmed的提前到期事件会把未来项目移入当前到期金额；合同中的可能性不会自动触发。",
            "平台或催收显示金额作为对方主张记录，仅用于比较，不会覆盖重建结果。",
        ],
    }


def yuan(value: object) -> str:
    return f"¥{dec(value):,.2f}"


def markdown_breakdown(values: dict) -> list[str]:
    if not values:
        return ["- 无"]
    return [f"- {CATEGORY_LABELS.get(category, category)}：{yuan(value)}" for category, value in values.items()]


def markdown_full(result: dict) -> str:
    current = result["as_of"]
    costs = result["cost_analysis"]
    relationships = result["relationship_summary"]
    creditor_names = "、".join(item["name"] for item in relationships["last_confirmed_creditors"]) or "尚未确认"
    creditor_candidates = "、".join(item["name"] for item in relationships["creditor_candidates"])
    collector_names = "、".join(item["name"] for item in relationships["collectors"]) or "未记录"
    lines = [
        f"# {result['case_name']}",
        "",
        f"计算至：{current['target_date']}",
        "",
        "## 债权关系",
        "",
        f"- {'涉及债权的机构（各自余额待核对）' if relationships['ownership_scope_unresolved'] else '最后能够确认的债权人'}：{creditor_names}",
        *( [f"- 尚待个案材料确认的债权人候选：{creditor_candidates}"] if creditor_candidates else [] ),
        f"- 已记录的催收执行方：{collector_names}",
        "- 催收执行方不因发送账单或联系借款人而自动成为债权人。",
        "",
        "## 核心结果",
        "",
        f"- 实际到账：{yuan(current['amount_received'])}",
        f"- 已记录还款：{yuan(current['total_repayments_recorded'])}",
        f"- 剩余本金：{yuan(current['remaining_principal'])}",
        f"- 当前已到期：{yuan(current['amount_due_now'])}",
        f"- 未来计划金额：{yuan(current['future_scheduled_total'])}",
        f"- 已知剩余总额：{yuan(current['total_remaining_before_unknown_costs'])}",
        "",
        "## 当前到期构成",
        "",
        *markdown_breakdown(current["due_now"]),
    ]

    lines.extend(["", "## 融资成本", ""])
    if costs["normal_financing_cost"] is not None:
        lines.append(f"- 正常履约融资成本：{yuan(costs['normal_financing_cost'])}")
    if costs["all_in_annualized_cost_pct"] is not None:
        lines.append(f"- 正常履约综合年化成本：{costs['all_in_annualized_cost_pct']}%")

    claim = current.get("balance_claim")
    if claim:
        lines.extend([
            "",
            "## 对方主张金额核对",
            "",
            f"- {claim['date']}由{claim['party']}主张：{yuan(claim['amount'])}",
        ])
        if claim["comparable_on_target_date"]:
            lines.extend([
                f"- 与当前到期金额之差：{yuan(claim['difference_from_due_now'])}",
                f"- 与已知剩余总额之差：{yuan(claim['difference_from_total_remaining'])}",
            ])
        else:
            lines.append("- 主张日期与测算日期不同，差额暂不比较。")

    if result["forecasts"]:
        lines.extend(["", "## 不新增还款时的预测", "", "| 日期 | 当前到期 | 剩余本金 | 已知剩余总额 |", "| --- | ---: | ---: | ---: |"])
        for forecast in result["forecasts"]:
            lines.append(
                f"| {forecast['target_date']} | {yuan(forecast['amount_due_now'])} | "
                f"{yuan(forecast['remaining_principal'])} | {yuan(forecast['total_remaining_before_unknown_costs'])} |"
            )

    sensitivity = current.get("allocation_sensitivity")
    if sensitivity:
        due_range = sensitivity["amount_due_now_range"]
        total_range = sensitivity["total_remaining_range"]
        lines.extend([
            "",
            "## 抵扣顺序不明时的区间",
            "",
            f"- 当前到期金额：{yuan(due_range['min'])} 至 {yuan(due_range['max'])}",
            f"- 已知剩余总额：{yuan(total_range['min'])} 至 {yuan(total_range['max'])}",
            f"- {sensitivity['reason']}",
        ])

    lines.extend(["", "## 提醒", ""])
    warnings = current["warnings"] + relationships["warnings"] + costs["warnings"]
    lines.extend([f"- {warning}" for warning in warnings] or ["- 当前没有自动生成的异常提醒。"])
    if result["unknown_items"]:
        lines.extend(["", "## 尚未确认", ""])
        lines.extend([f"- {item}" for item in result["unknown_items"]])
    lines.extend([
        "",
        "本结果用于根据现有协议和交易记录重建账目，不判断条款最终是否具有法律效力。",
    ])
    return "\n".join(lines)


def markdown_concise(result: dict) -> str:
    current = result["as_of"]
    relationships = result["relationship_summary"]
    confidence = result["evidence_confidence"]
    costs = result["cost_analysis"]
    weakest = "、".join(SECTION_LABELS.get(name, name) for name in confidence["weakest_material_sections"])
    creditors = "、".join(item["name"] for item in relationships["last_confirmed_creditors"]) or "尚未确认"
    creditor_candidates = "、".join(item["name"] for item in relationships["creditor_candidates"])
    claim = current.get("balance_claim")

    conclusion = (
        f"截至{current['target_date']}，重建的当前到期金额为{yuan(current['amount_due_now'])}，"
        f"剩余本金为{yuan(current['remaining_principal'])}。"
    )
    if claim:
        conclusion += f"对方于{claim['date']}主张{yuan(claim['amount'])}。"
        if claim["comparable_on_target_date"]:
            conclusion += f"与按现有材料计算的剩余总额相差{yuan(claim['difference_from_total_remaining'])}。"
        else:
            conclusion += "日期不同，暂不比较差额。"

    lines = [
        f"# {result['case_name']}",
        "",
        conclusion,
        f"已知剩余总额：{yuan(current['total_remaining_before_unknown_costs'])}"
        f"（当前到期{yuan(current['amount_due_now'])} + 未到期计划{yuan(current['future_scheduled_total'])}）。",
        "",
        f"可信度：**{confidence['overall']['grade']} · {confidence['overall']['label']}**（最弱项：{weakest}）",
    ]
    if costs["all_in_annualized_cost_pct"] is not None:
        lines.extend(["", f"正常履约综合年化成本：**{costs['all_in_annualized_cost_pct']}%**"])
    lines.extend([
        "",
        "## 当前到期构成",
        "",
        *markdown_breakdown(current["due_now"]),
        "",
        "## 债权关系",
        "",
        f"- {'涉及债权的机构（各自余额待核对）' if relationships['ownership_scope_unresolved'] else '最后能够确认的债权人'}：{creditors}",
    ])
    if creditor_candidates:
        lines.append(f"- 协议显示但尚待个案材料确认：{creditor_candidates}")
    if relationships["ownership_scope_unresolved"]:
        lines.append("- 部分代偿或转让的范围尚未厘清，不能把同一笔余额重复计给各方。")

    if result["forecasts"]:
        lines.extend(["", "## 无新增还款时的预测", "", "包含未来分期到期与已知费用；未计入未知收费或未确认事件。"])
        for forecast in result["forecasts"]:
            lines.append(
                f"- {forecast['target_date']}：按现有材料预计剩余{yuan(forecast['total_remaining_before_unknown_costs'])}"
            )

    sensitivity = current.get("allocation_sensitivity")
    if sensitivity:
        due_range = sensitivity["amount_due_now_range"]
        lines.extend([
            "",
            f"还款抵扣顺序尚未确认，当前到期金额可能在{yuan(due_range['min'])}至{yuan(due_range['max'])}之间。",
        ])

    critical = [warning for warning in current["warnings"] if "完整性" in warning or "缺期" in warning]
    warnings = list(dict.fromkeys(critical + costs["warnings"] + current["warnings"] + relationships["warnings"]))
    if warnings:
        lines.extend(["", "## 需要注意", ""])
        lines.extend([f"- {warning}" for warning in warnings[:4]])
        if len(warnings) > 4:
            lines.append(f"- 另有{len(warnings) - 4}项提醒，完整结果中可查看。")

    if result["unknown_items"]:
        lines.extend(["", "## 还缺什么", ""])
        lines.extend([f"- {item}" for item in result["unknown_items"][:3]])
        if len(result["unknown_items"]) > 3:
            lines.append(f"- 另有{len(result['unknown_items']) - 3}项待确认材料。")

    lines.extend(["", "这是依据现有材料重建的账目，不是对条款法律效力的结论。"])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--detail", choices=("concise", "full"), default="concise")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = calculate(data)
        if args.format == "markdown":
            output = markdown_full(result) if args.detail == "full" else markdown_concise(result)
        else:
            output = json.dumps(result, ensure_ascii=False, indent=2, default=serialize)
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
    except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
