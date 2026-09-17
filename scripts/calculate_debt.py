#!/usr/bin/env python3
"""Calculate traceable normal and overdue consumer-loan scenarios."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, getcontext
from pathlib import Path

getcontext().prec = 28
CENT = Decimal("0.01")


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


def validate(data: dict) -> None:
    for key in ("case_name", "principal", "term_months", "annual_interest_rate_pct", "overdue_snapshots_days"):
        if key not in data:
            raise ValueError(f"missing required field: {key}")
    if dec(data["principal"]) <= 0:
        raise ValueError("principal must be positive")
    if dec(data["term_months"]) <= 0 or dec(data["term_months"]) != int(data["term_months"]):
        raise ValueError("term_months must be positive")
    for field in ("annual_interest_rate_pct", "guarantee_annual_rate_pct", "penalty_interest_multiplier", "overdue_liquidated_daily_rate_pct"):
        if field in data and dec(data[field]) < 0:
            raise ValueError(f"{field} cannot be negative")
    if dec(data.get("days_per_period", 30)) <= 0 or dec(data.get("days_per_period", 30)) != int(data.get("days_per_period", 30)):
        raise ValueError("days_per_period must be a positive integer")
    if data.get("repayment_method", "equal_payment") != "equal_payment":
        raise ValueError("this version supports repayment_method=equal_payment only")
    if any(dec(day) < 0 or dec(day) != int(day) for day in data["overdue_snapshots_days"]):
        raise ValueError("overdue snapshot days must be non-negative integers")


def build_schedule(data: dict) -> list[dict]:
    principal = dec(data["principal"])
    periods = int(data["term_months"])
    monthly_rate = dec(data["annual_interest_rate_pct"]) / Decimal("100") / Decimal("12")
    guarantee_monthly = principal * dec(data.get("guarantee_annual_rate_pct", 0)) / Decimal("100") / Decimal("12")

    if monthly_rate == 0:
        payment = principal / periods
    else:
        factor = (Decimal("1") + monthly_rate) ** periods
        payment = principal * monthly_rate * factor / (factor - Decimal("1"))

    balance = principal
    schedule = []
    for period in range(1, periods + 1):
        interest = balance * monthly_rate
        principal_part = payment - interest
        if period == periods:
            principal_part = balance
            payment_now = principal_part + interest
        else:
            payment_now = payment
        balance -= principal_part
        schedule.append({
            "period": period,
            "principal": principal_part,
            "interest": interest,
            "principal_interest": payment_now,
            "guarantee_fee": guarantee_monthly,
            "total": payment_now + guarantee_monthly,
            "balance_after": max(balance, Decimal("0")),
        })
    return schedule


def overdue_snapshot(data: dict, schedule: list[dict], days: int) -> dict:
    period_days = int(data.get("days_per_period", 30))
    loan_annual = dec(data["annual_interest_rate_pct"]) / Decimal("100")
    penalty_annual = loan_annual * dec(data.get("penalty_interest_multiplier", 0))
    damages_daily = dec(data.get("overdue_liquidated_daily_rate_pct", 0)) / Decimal("100")

    due = []
    for index, row in enumerate(schedule):
        due_day = index * period_days
        if due_day < days:
            late_days = days - due_day
            due.append((row, late_days))

    due_principal = sum((row["principal"] for row, _ in due), Decimal("0"))
    due_interest = sum((row["interest"] for row, _ in due), Decimal("0"))
    due_guarantee = sum((row["guarantee_fee"] for row, _ in due), Decimal("0"))
    penalty_interest = sum((row["principal"] * penalty_annual / Decimal("365") * late for row, late in due), Decimal("0"))
    liquidated = sum((row["principal"] * damages_daily * late for row, late in due), Decimal("0"))
    known_due = due_principal + due_interest + due_guarantee + penalty_interest + liquidated

    acceleration = data.get("acceleration") or {}
    threshold = acceleration.get("possible_after_days")
    risk = None
    if threshold is not None and days >= int(threshold):
        original_principal = dec(data["principal"])
        guarantee_total = sum((row["guarantee_fee"] for row in schedule), Decimal("0"))
        extra_penalty = original_principal * dec(acceleration.get("original_principal_penalty_pct", 0)) / Decimal("100")
        guarantee_due = guarantee_total if acceleration.get("remaining_guarantee_fees_due", False) else due_guarantee
        risk_total = original_principal + due_interest + guarantee_due + penalty_interest + liquidated + extra_penalty
        risk = {
            "status": "possible, not assumed to have occurred",
            "entire_outstanding_principal_due": money(original_principal),
            "normal_interest_due_to_snapshot": money(due_interest),
            "guarantee_fees_due": money(guarantee_due),
            "penalty_interest": money(penalty_interest),
            "liquidated_damages": money(liquidated),
            "acceleration_guarantee_penalty": money(extra_penalty),
            "risk_total_excluding_unknown_costs": money(risk_total),
        }

    return {
        "overdue_days": days,
        "missed_installments": len(due),
        "overdue_principal": money(due_principal),
        "scheduled_interest_due": money(due_interest),
        "guarantee_fee_due": money(due_guarantee),
        "penalty_interest": money(penalty_interest),
        "liquidated_damages": money(liquidated),
        "known_due_total": money(known_due),
        "total_principal_still_unpaid": money(dec(data["principal"])),
        "acceleration_risk": risk,
    }


def serialize(value):
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    raise TypeError(type(value).__name__)


def calculate(data: dict) -> dict:
    validate(data)
    schedule = build_schedule(data)
    total_pi = sum((row["principal_interest"] for row in schedule), Decimal("0"))
    total_guarantee = sum((row["guarantee_fee"] for row in schedule), Decimal("0"))
    normal_total = total_pi + total_guarantee
    unknown_costs = list(data.get("unknown_cost_items", []))
    for field, label in (("guarantee_annual_rate_pct", "担保费用"),
                         ("penalty_interest_multiplier", "逾期罚息"),
                         ("overdue_liquidated_daily_rate_pct", "逾期违约金")):
        if field not in data:
            unknown_costs.append(f"{label}未提供计费规则，未计入金额；不能据此认定该项费用为零。")
    if data.get("compound_unpaid_interest"):
        unknown_costs.append("模型未计算复利，合同约定的复利可能增加实际金额。")
    snapshots = [overdue_snapshot(data, schedule, int(day)) for day in data["overdue_snapshots_days"]]

    acceleration = data.get("acceleration") or {}
    threshold = acceleration.get("possible_after_days")
    threshold_result = None
    if threshold is not None:
        threshold_result = overdue_snapshot(data, schedule, int(threshold))

    return {
        "case_name": data["case_name"],
        "status": "simulation",
        "simulation_notice": data.get("simulation_notice") or "等额本息、固定间隔的模型模拟；未纳入实际还款记录，不能作为已核实欠款。",
        "origination": {
            "amount_received": money(dec(data["principal"])),
            "monthly_principal_interest": money(schedule[0]["principal_interest"]),
            "monthly_guarantee_fee": money(schedule[0]["guarantee_fee"]),
            "normal_total_principal_interest": money(total_pi),
            "normal_total_guarantee_fee": money(total_guarantee),
            "normal_total_repayment": money(normal_total),
            "normal_financing_cost": money(normal_total - dec(data["principal"])),
        },
        "overdue_snapshots": snapshots,
        "acceleration_threshold_snapshot": threshold_result,
        "unknown_cost_items": list(dict.fromkeys(unknown_costs)),
        "sources": data.get("sources", []),
        "method_notes": [
            "Overdue days are counted from the first missed due date; a boundary-day snapshot excludes the next installment due that day.",
            "Penalty interest and liquidated damages are shown together because the sample disclosure lists different charging parties; actual signed documents control.",
            "Compound interest is not quantified in this version and remains an unknown item when the contract permits it.",
            "Acceleration and guarantee compensation are events, not automatic arithmetic assumptions; the risk total is separate from the ordinary overdue total.",
        ],
    }


def yuan(value: str | Decimal) -> str:
    return f"¥{dec(value):,.2f}"


def markdown(result: dict) -> str:
    origin = result["origination"]
    lines = [
        f"# {result['case_name']}",
        "",
        f"> {result.get('simulation_notice') or '以下按已提供合同数据计算。'}",
        "",
        "## 首次借款",
        "",
        f"- 实际取得本金：{yuan(origin['amount_received'])}",
        f"- 每期本息：{yuan(origin['monthly_principal_interest'])}",
        f"- 每期担保费：{yuan(origin['monthly_guarantee_fee'])}",
        f"- 正常履约总还款：{yuan(origin['normal_total_repayment'])}",
        f"- 正常履约融资成本：{yuan(origin['normal_financing_cost'])}",
        "",
        "## 逾期节点",
        "",
        "| 逾期时间 | 已逾期期数 | 到期本金 | 正常利息 | 担保费 | 罚息 | 逾期违约金 | 已知到期合计 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for snap in result["overdue_snapshots"]:
        lines.append(
            f"| {snap['overdue_days']}天 | {snap['missed_installments']} | {yuan(snap['overdue_principal'])} | "
            f"{yuan(snap['scheduled_interest_due'])} | {yuan(snap['guarantee_fee_due'])} | "
            f"{yuan(snap['penalty_interest'])} | {yuan(snap['liquidated_damages'])} | {yuan(snap['known_due_total'])} |"
        )

    threshold = result.get("acceleration_threshold_snapshot")
    if threshold and threshold.get("acceleration_risk"):
        risk = threshold["acceleration_risk"]
        lines.extend([
            "",
            "## 风险跳点",
            "",
            f"到逾期第{threshold['overdue_days']}天，合同模板允许相关方选择宣布提前到期。若该权利被实际行使且担保责任发生，模型风险金额为 **{yuan(risk['risk_total_excluding_unknown_costs'])}**。这不是自动发生的余额。",
            "",
            f"其中包括全部未偿本金{yuan(risk['entire_outstanding_principal_due'])}、已到期正常利息{yuan(risk['normal_interest_due_to_snapshot'])}、担保费{yuan(risk['guarantee_fees_due'])}、罚息{yuan(risk['penalty_interest'])}、逾期违约金{yuan(risk['liquidated_damages'])}及加速/担保违约金{yuan(risk['acceleration_guarantee_penalty'])}。",
        ])

    lines.extend(["", "## 尚未计入", ""])
    for item in result["unknown_cost_items"]:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "本结果用于读懂合同和核对账目，不判断条款最终是否具有法律效力。真实余额以签署文件、实际付款、代偿/转让通知和对账记录为准。",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        result = calculate(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(markdown(json.loads(json.dumps(result, default=serialize))))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=serialize))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
