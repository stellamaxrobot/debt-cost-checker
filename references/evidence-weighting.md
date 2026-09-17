# Evidence Weighting

Use evidence weights to resolve conflicts and describe confidence. They are decision priorities, not statistical probabilities and not a judgment about whether a document is legally enforceable.

## Base Weights

| `evidence_type` | Weight | Typical use |
| --- | ---: | --- |
| `bank_transaction` | 100 | Actual disbursement, repayment, refund and reversal |
| `court_finding` | 98 | Contract, payment, compensation, assignment or fee fact expressly found after judicial review |
| `signed_case_document` | 95 | Rate, fee rule, repayment schedule and allocation order for this loan |
| `platform_itemized_statement` | 88 | Dated ledger entries and balance components downloadable for this loan |
| `official_notice` | 85 | Acceleration, compensation, assignment or restructuring event |
| `app_screenshot` | 68 | Dated displayed balance or schedule when export is unavailable |
| `collector_written_statement` | 50 | Amount or creditor identity claimed by a collector |
| `borrower_recollection` | 35 | Approximate amount or date remembered by the borrower |
| `public_template` | 20 | Possible clause structure when the signed case document is unavailable |
| `unknown` | 10 | Unidentified source |

If a record has no source reference, cap its weight at 55. A `claimed`, `contractual_only` or `unknown` status does not become confirmed merely because the document type normally carries a high weight.

## Field-Specific Priority

- **Money actually moved:** bank/payment transaction > platform itemized ledger > app screenshot > recollection.
- **Rate, fee and allocation rule:** signed case-specific agreement or cost disclosure > itemized statement > app screenshot > public template.
- **Compensation or assignment:** court finding or dated official notice plus amount/payment evidence > written claim > contractual permission in the original agreement.
- **Current balance:** reconstructed ledger from stronger component evidence > itemized platform statement > screenshot > collector demand.

Never use a public template to overwrite a blank or different field in the user's signed agreement.

## Conflict Handling

When two sources disagree:

1. Keep both values and their sources.
2. Choose the higher-priority value only for a labeled calculation scenario.
3. Show the difference when it changes principal, payment history, creditor identity or fees.
4. Ask for the smallest next item that can resolve the conflict.

Do not average contradictory amounts or dates.

## Section Confidence

Score these sections separately:

- amount received;
- repayment history;
- contractual schedule;
- fee rules;
- creditor relationship.

The overall calculation confidence is the lowest score among the material calculation sections. Do not average the scores: one weak critical field can limit the whole result.

| Grade | Score | User-facing label |
| --- | ---: | --- |
| A | 90-100 | 证据充分 |
| B | 75-89 | 较可靠 |
| C | 55-74 | 部分推算 |
| D | 35-54 | 仅供估算 |
| E | 0-34 | 信息不足 |

Keep the weight and reason available in structured output. In the concise report, show only the grade, label and weakest material section.

Evidence for an individual payment does not establish a complete repayment history. Require both `repayment_history_complete: true` and sourced `repayment_history_evidence` before giving the history a strong score. An unverified history or incomplete normal schedule caps the affected section at 10 (E). Known but excluded fee rules cap fee-rule confidence at 20. Confirmed acceleration events that change amounts are another material section. Only transactions on/before the calculation date contribute to current confidence. Creditor confidence remains separate from amount confidence.
