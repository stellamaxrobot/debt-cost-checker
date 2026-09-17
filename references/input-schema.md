# Input Schema

The scripts accept one JSON object. Use the small simulation format for prospective calculations and the event-ledger format for an existing debt.

## Existing Debt Ledger

Use `scripts/reconstruct_debt.py` and validate the structure against `schemas/overdue-case.schema.json`. The engine supports these collections:

| Collection | Purpose |
| --- | --- |
| `entities[]` | Platform, lender, guarantor, counter-guarantor, insurer, service provider, assignee and collector. Add `status`; use `contractual_only` for a party named only in an unsigned public template. |
| `relationships[]` | Funding, service, guarantee, counter-guarantee, insurance, compensation, assignment and collection links |
| `disbursements[]` | Dated cash received for this single loan; analyze separate loans in separate files |
| `scheduled_payments[]` | Contractual due dates and components |
| `opening_balance` | Court-, notice- or statement-confirmed balance components used to start a post-compensation recovery ledger |
| `transactions[]` | Dated repayments and waivers; refunds/reversals need manual reconciliation |
| `fee_rules[]` | Charging party, base, rate, frequency and start/end triggers |
| `events[]` | Only confirmed acceleration changes the ledger; other event types need separately modeled rules/relationships |
| `balance_claims[]` | Amounts displayed or demanded on specific dates |

Each record should carry a source reference, `evidence_type` from [evidence-weighting.md](evidence-weighting.md), and, where relevant, `status: confirmed|claimed|inferred|assumed|contractual_only|unknown`.

Minimum executable input requires:

- `case_name`;
- `as_of_date`;
- `amount_received` or `disbursements[]`;
- at least one `scheduled_payments[]` row, or one `opening_balance` for a post-compensation recovery ledger.

Set `case_scope: post_compensation_recovery` when the reliable evidence begins with a dated compensation or recovery balance but the original installment ledger is incomplete. Split `opening_balance.components` into principal, interest, penalty interest and other supported categories. This mode calculates forward from that date and deliberately does not invent earlier repayments or recompute normal all-in cost without the original schedule.

An opening balance is an end-of-day snapshot: do not combine it with `scheduled_payments`, and include only transactions after its date. Earlier payments must already be reflected in the opening amount. Rules cannot start before that date.

Set `repayment_history_complete: true` only after reconciling all repayment channels for the covered period, with a sourced `repayment_history_evidence` record. Otherwise the repayment-history confidence is E even when individual receipts are strong evidence. Set `normal_schedule_complete: true` only when all installments and required normal fees have been checked. An incomplete schedule has no definitive total financing cost or XIRR output.

For every scheduled row, put the date in `due_date` and split `components` into `principal`, `normal_interest`, `guarantee_fee`, `insurance_fee`, `service_fee` or another supported category. Do not store one unexplained installment total when its components are available.

Record actual payments and contractual waivers in `transactions[]`. Each transaction needs an exact date and amount. A remembered aggregate payment with no dates belongs in `unknown_items`, not in the executable transaction list.

Record the sourced payment-allocation sequence in `allocation_order`. When it is absent, the engine uses a disclosed scenario order and warns that the balance is only an estimate.
When dated payments are available, it also reports the balance range produced by principal-first and fees-first allocation scenarios.

Each `fee_rules[]` item needs:

- fee category and charging label;
- calculation base;
- rate unit and rate value;
- grace period through `start_after_days`, when applicable;
- explicit `starts_on` for rules based on all outstanding principal or the original amount received;
- evidence status and source clause.

Only confirmed or explicitly included rules affect the total. Claimed and unknown fee rules remain outside the numeric result by default.

Use `events[]` for delinquency, acceleration, guarantee compensation, assignment and restructuring. Only a `confirmed` acceleration event changes the arithmetic. Compensation and assignment remain part of the relationship timeline unless a separately supported fee or balance rule changes the amount.

Use `relationships[]` direction consistently:

- lender -> borrower for `funded`;
- counter-guarantor -> guarantor for `counter_guaranteed`;
- previous creditor -> assignee for `assigned`;
- compensating party -> paid creditor for `compensated`;
- collector -> represented creditor for `collects_for`.

A confirmed relationship without `effective_date` remains visible but does not change the last-confirmed-creditor result. A confirmed compensation changes the creditor only when `subrogation_confirmed` is also supported. For assignment and compensation, use `scope: full|partial|unknown`: only `full` replaces the prior creditor; the other scopes retain both and require amount reconciliation. Entity names/roles alone do not confirm ownership.

Use a case-specific institutional agreement, court finding or official disclosure to confirm `counter_guaranteed`. A generic industry article may explain the structure but cannot confirm it for a particular loan. Counter-guarantee records are contextual and never change the debt total or last-confirmed-creditor result by themselves.

Use `balance_claims[]` for dated amounts displayed or demanded by a platform, creditor or collector. A claim is compared only on the same date as the reconstruction; a stale claim has null difference fields. A claim never replaces the reconstructed amount.

Use `forecast_dates[]` for future no-new-payment checkpoints. Forecasts retain transactions through `as_of_date`, exclude later payments/waivers, and include scheduled obligations and supported fee rules that become active by then. They do not compare a future balance with an old claim.

Use `risk_context` for comparison values that should trigger a cost reminder:

- `nominal_annual_rate_pct` from the signed loan document;
- `high_cost_attention_pct` and `high_cost_attention_source` for normal all-in cost;
- `overdue_cost_attention_pct` and `overdue_cost_attention_source` for combined overdue rates.

An attention line without a source remains a user-configured heuristic. It must never be described as a legal cap. When dated disbursements and the full normal repayment schedule are present, the engine calculates date-based all-in annualized cost from actual cash received and all required normal payments.

## Before-Borrowing Simulation

The older deterministic script `scripts/calculate_debt.py` uses the single-loan fields below:

## Required Fields

| Field | Type | Meaning |
| --- | --- | --- |
| `case_name` | string | Human-readable case label |
| `principal` | number | Amount actually advanced to the borrower |
| `term_months` | integer | Number of repayment periods |
| `annual_interest_rate_pct` | number | Contract nominal annual loan rate in percent |
| `overdue_snapshots_days` | number array | Days counted from the first missed due date |

## Optional Fields

| Field | Default | Meaning |
| --- | --- | --- |
| `repayment_method` | `equal_payment` | Currently supported method |
| `days_per_period` | `30` | Simulation spacing between due dates |
| `guarantee_annual_rate_pct` | `0` | Annual guarantee fee on original principal |
| `penalty_interest_multiplier` | unknown, excluded | Overdue annual rate divided by loan annual rate |
| `overdue_liquidated_daily_rate_pct` | `0` | Daily damages rate in percent on overdue principal |
| `compound_unpaid_interest` | `false` | Kept as a warning; the first version does not quantify compound interest |
| `acceleration.possible_after_days` | omitted | First overdue day when acceleration may be exercised |
| `acceleration.original_principal_penalty_pct` | `0` | Additional penalty if acceleration and guarantee liability occur |
| `acceleration.remaining_guarantee_fees_due` | `false` | Whether all unpaid future guarantee fees become due |
| `unknown_cost_items` | empty array | Contractual costs with no fixed amount |
| `sources` | empty array | Document, clause and URL records supporting the input |

## Timing Convention

The shortcut calculator always labels its result as a simulation. Missing guarantee/penalty/damages rules are listed as unknown and excluded from numeric totals, not confirmed zero fees. Compounding is not calculated. Monthly rate equivalents in the ledger use the same `month_days` divisor as accrual and a 365-day projection year.

`overdue_snapshots_days` starts at the first missed repayment date. A 30-day snapshot includes the first missed installment and is measured just before the next scheduled installment becomes due. This convention avoids counting two installments at the exact boundary.

Acceleration is calculated separately. A clause saying “超过90日” is represented as `possible_after_days: 91`; the 90-day ordinary overdue result therefore remains distinct from the 91-day risk event.

## Unsupported Or Unknown Values

Do not invent:

- actual guarantee compensation date;
- creditor-transfer date;
- collection, litigation, legal, valuation or travel costs;
- discretionary fee waivers;
- a rate left blank in a public template.

Keep them in `unknown_cost_items` until supported by a signed document or transaction record.
