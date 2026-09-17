---
name: debt-cost-checker
description: Extract loan, guarantee, insurance, service and overdue terms from signed consumer-loan documents, then calculate repayment and overdue-cost scenarios with source-linked assumptions and explicit uncertainty. Use when someone wants to understand an existing debt, compare a loan before borrowing, or model missed-payment consequences. Do not use to decide legal enforceability or fabricate values missing from the signed documents.
---

# Debt Cost Checker

Turn a borrower's actual contract package into a traceable debt calculation and debt-relationship map. Assume the user may know only the platform, amount borrowed, balance currently shown and number of missed installments. Do not require the user to understand lenders, guarantors, compensation or assignment before starting.

Keep three things separate throughout the work:

1. **Signed facts**: values present in the signed agreement, IOU, repayment plan or cost disclosure.
2. **Simulation assumptions**: values chosen only to illustrate a possible loan.
3. **Unknown contingent costs**: fees described without a fixed amount, such as litigation, collection or valuation costs.

Never silently replace a missing value with zero. Continue with partial information when possible, show a range or unresolved difference, and ask only for the next document or fact that materially changes the result.

## Adapt Before Specializing

Normalize documents into the common ledger schema instead of assuming a platform name, fixed contract title or repayment method. Explicit dated schedule components support equal payment, equal principal, interest-only, bullet and irregular plans without platform-specific arithmetic.

The ledger currently handles one CNY loan at a time. Analyze multiple loans separately before summarizing. Refunds/reversals, early repayments, compounding, restructuring and partial creditor-balance allocation are not automatically modeled. Preserve these as unresolved items or use an explicitly supported revised opening balance; do not squeeze them into a normal repayment entry. An unmatched early payment means the modeled balance is unresolved, not a verified amount owed.

Add a platform-specific mapping only when the platform uses a stable field name or document layout that improves extraction. Keep calculation, evidence weighting and warnings platform-neutral. When a new agreement contains an unsupported fee base or trigger, preserve it as unknown and explain the missing rule rather than forcing it into the closest existing category.

## Start With What The User Knows

Accept a minimal intake:

- platform name;
- approximate borrowing date;
- amount the user remembers receiving;
- balance currently shown or demanded;
- number of missed installments;
- available agreements or screenshots.

Do not block the analysis because the user cannot remember the original rate or past payments. Mark those facts as unknown, inspect the agreements, and produce an initial debt map plus a targeted evidence list. Treat an app balance, collection message or phone statement as a `claimed balance`, not a verified amount.

## Collect The Contract Package

Ask for or identify these documents before giving a personal calculation:

- `个人贷款综合融资成本明示表`
- signed loan contract and electronic IOU
- repayment plan
- guarantee, credit insurance or other credit-enhancement agreement
- service or consulting agreement
- debit and automatic-repayment authorization
- compensation, subrogation, acceleration or debt-transfer notice, if one has occurred
- the signing page showing the total number of documents

Separate borrower-facing documents from institution-to-institution documents. A counter-guarantee or risk-sharing agreement is commonly signed between the platform, lender and credit-enhancement provider and may never appear in the borrower's app contract center. Do not call the borrower package incomplete merely because that internal agreement is unavailable. Record the counter-guarantee only when a case-specific institutional agreement, court finding or official disclosure supports it; otherwise label the relationship `claimed` or `unknown`. An industry description of a common structure is context, not proof that the structure applied to this loan.

If only a platform name or public template is available, produce a clearly labeled simulation. Mark template-derived entities and relationships as `contractual_only`; a named lender in an unsigned public template is a creditor candidate, not the borrower's confirmed creditor. Do not present simulated values as the borrower's actual balance.

## Extract Terms With Provenance

For every rate, fee, date and trigger, record the document title and clause or table row. Read [input-schema.md](references/input-schema.md) when preparing structured input.

Assign an `evidence_type` to each material record and read [evidence-weighting.md](references/evidence-weighting.md) before resolving conflicting facts. Treat weights as source precedence, not probability. Report confidence by section and let the weakest material calculation section limit the overall grade.

Check completeness separately from authenticity: a bank receipt proves one payment, not the absence of other payments. Set `repayment_history_complete: true` only after the covered period and repayment channels have been reconciled, with `repayment_history_evidence`. Set `normal_schedule_complete: true` only when all contractual installments and required normal fees have been checked. Without completeness evidence, return a partial reconstruction and suppress a definitive all-in cost.

Pay special attention to:

- whether the rate applies to original principal, outstanding principal, overdue principal, unpaid interest or a fixed amount;
- whether a quoted percentage is daily, monthly, annual or an IRR disclosure;
- whether penalty interest and liquidated damages run concurrently;
- whether unpaid interest or penalty interest compounds;
- whether acceleration or guarantee compensation is automatic, optional or dependent on notice;
- whether compensation changes the creditor and starts a new liquidated-damages rule;
- payment allocation order, because a payment may reduce fees before principal.

Also identify every named role and relationship. Read [debt-relationship-model.md](references/debt-relationship-model.md) when a contract package involves more than one company or contains guarantee, insurance, compensation, subrogation or assignment language.

## Reconstruct The Debt

Build a chronological ledger when the loan is already overdue:

1. Record each disbursement and scheduled installment.
2. Record supported actual repayments and waivers. Identify refunds and reversals separately for manual reconciliation. If payment history is missing, keep `paid amount unknown`; do not assume no payment.
3. Apply the contract's payment-allocation order only when it is stated and the transaction data supports it.
4. Add interest and fees according to each rule's base, rate, start date and charging party.
5. Apply acceleration, compensation and assignment only when the trigger and actual event evidence are distinguished. A contractual right to accelerate is not proof that acceleration occurred.
6. Compare the reconstructed amount with a platform or collector balance claim only when dates match. Otherwise retain the dated claim and request or reconstruct a matching-date balance.

When a court finding, compensation notice or itemized statement confirms the balance at compensation but the earlier installment ledger is incomplete, use `case_scope: post_compensation_recovery` with `opening_balance`. Calculate forward from the confirmed principal and interest components; do not invent pre-compensation repayments. Keep the original disbursement as provenance, and state that normal all-in cost cannot be recomputed without the original schedule.

An opening balance is an end-of-day snapshot. Do not combine it with the original installment schedule or replay payments on/before its date. For a creditor change, record `scope: full|partial|unknown`; only an evidenced full transfer removes the prior creditor. Partial/unknown scope retains both parties with a warning about the unresolved allocation. A lender name alone does not establish current ownership; use dated relationship evidence.

For incomplete cases, report a lower bound, an upper scenario when supportable, and the missing evidence that separates them.

## Choose The Calculation Mode

Use `scripts/calculate_debt.py` only for a before-borrowing or contract-only equal-payment simulation where no actual repayment history needs to be reconciled.

Use `scripts/reconstruct_debt.py` when the borrower has an existing loan and any dated repayment, waiver, balance claim or confirmed acceleration event. Read [input-schema.md](references/input-schema.md), then build input conforming to [overdue-case.schema.json](schemas/overdue-case.schema.json).

The reconstruction engine:

- adds each scheduled principal, interest and fee component on its due date;
- accrues confirmed daily, monthly or annualized overdue rules;
- applies each repayment using the sourced allocation order;
- moves future principal into the due balance only for a confirmed acceleration event;
- separates current due amount, future scheduled amount and the counterparty's claimed balance;
- projects future checkpoints without assuming undocumented future payments.

When payments exist but the allocation order is not supported by the materials, present the engine's principal-first and fees-first sensitivity range. Do not describe either scenario as the actual platform balance.

## Calculate

Use `scripts/calculate_debt.py` for deterministic equal-payment simulations. The script returns:

- the normal repayment plan and total normal cost;
- known amounts due after selected overdue durations;
- a separate acceleration-risk estimate when the input enables it;
- unknown items that remain outside the numeric total.

Run:

```bash
python3 scripts/calculate_debt.py /path/to/private-simulation.json --format markdown
```

For an existing overdue debt, run:

```bash
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format markdown
```

Public examples contain fictional output only. When preparing a private case copy for an explicitly requested recipient, `scripts/redact_case.py` can assist with structured JSON redaction. Manually review the result; this helper does not sanitize the original PDF, image metadata or every possible free-text identifier:

```bash
python3 scripts/redact_case.py private-case.json shareable-case.json
```

For a real borrower, replace every simulated value with the signed value and preserve `source` fields. Never copy the fictional example's fee rules into a real case. If the payment-allocation order is missing, retain the engine warning and present the result as an estimate.

## Present Results

Default to a concise result. Keep zero-value categories, formulas, method notes, full allocation entries and repeated evidence citations out of the main response unless they explain a discrepancy or the user requests detail. The deterministic JSON remains the audit trail.

Show the concise result in this order:

1. current due amount, future scheduled amount, their sum, remaining principal (already included), and same-date claimed-balance difference;
2. confidence grade and weakest material section;
3. non-zero components labeled as current due amounts, not the entire remaining debt;
4. last confirmed creditor and any unresolved partial transfer;
5. high-cost, duplicated-charge and evidence-gap warnings;
6. up to three next documents that would materially improve the result.

For a full result, show:

1. money received and normal total repayment;
2. each requested overdue checkpoint with principal, normal interest, guarantee/insurance fee, penalty interest and liquidated damages separated;
3. event warnings for acceleration, compensation and creditor changes;
4. unknown costs not included in the total;
5. the exact documents or fields still needed for an actual calculation.

For users unfamiliar with online lending, keep these three questions visible:

- **Who currently claims the debt**: platform, original lender, guarantor/insurer, compensating party, assignee and collector, with evidence dates.
- **How the balance grew**: principal, normal interest, guarantee/insurance/service fees, penalty interest, liquidated damages, payments and unexplained difference.
- **What needs attention**: disclosure gaps, duplicated or overlapping charges, compounding, acceleration, compensation, assignment and unusually high all-in cost.

Read [risk-warnings.md](references/risk-warnings.md) before generating high-cost or legal-review warnings. Never label a loan illegal or usurious from a percentage alone.

Use calm, direct language. Translate terms such as subrogation and assignment into everyday Chinese. Do not shame the borrower or imply that a modeled event has already occurred. State that the calculation interprets documents and flags issues for review; it does not determine whether a term is legally enforceable.

For forecasts, state that no payments after `as_of_date` are included and that the total includes future contractual installments. Keep material missing-record, ownership and high-cost warnings visible even when shortening the report. Public-facing examples should show fictional output only; never include personal source materials in the README.
