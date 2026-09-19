**[Non-commercial license](LICENSE.md):** Free for non-commercial personal, educational, research, and public-interest use. Commercial use requires prior written permission. Source-available; not an OSI-approved open-source license.

<div align="center">

**English** | [简体中文](README.zh-CN.md)

# Debt Cost Checker

**Understand who you owe, what you are being charged, and how overdue costs may grow.**

债务算清楚 · Chinese consumer lending · Codex Skill · Alpha

[Sample Report](#sample-report) · [Getting Started](#getting-started) · [Scope](#scope)

</div>

Give Codex your loan agreements, statements, and repayment records to get a concise debt analysis. When records are incomplete, the skill explains which amounts remain uncertain and what evidence would help most.

Built for consumer loans in China, denominated in renminbi (CNY). An English README does not imply support for other jurisdictions. User-facing reports are in Chinese by default; the English example below illustrates the output structure.

## Sample Report

> This is a fictional output mockup. All dates, entities, and amounts are invented to illustrate the format. It is not a real case or a measured script result. No borrower input materials are published here.

### How Much of Your Balance Can We Account For?

**As of 2026-09-17, the amount currently due is CNY 8,240.**

| Measure | Illustrative result |
| :--- | ---: |
| Currently due | **CNY 8,240** |
| Scheduled amounts not yet due | CNY 4,120 |
| Known remaining total: the two amounts above combined | **CNY 12,360** |
| Total remaining principal, already included above | CNY 11,600 |
| Balance displayed by the platform on the same date | CNY 13,500 |
| Difference from the known remaining total | **CNY 1,140, to be checked** |

Remaining principal is already included in the total; do not add it again. Any reduction in future interest or fees upon early settlement must be checked separately.

**The CNY 8,240 currently due consists of:**

| Component | Amount |
| :--- | ---: |
| Principal due | CNY 7,600 |
| Regular interest | CNY 300 |
| Overdue penalty interest | CNY 140 |
| Guarantee fee | CNY 200 |

**Who is the creditor?**

Lender A is the last creditor supported by the available evidence. Guarantor B provided a guarantee, but there is no evidence that it has paid the lender on the borrower's behalf. Collection agency C handles repayment contact; that role alone does not establish ownership of the claim.

**What needs attention?**

- The platform's additional CNY 1,140 has not been linked to specific charges.
- The illustrative all-in annualized cost is 31.80%, compared with the stated contract rate of 18%; additional fees need review.
- Evidence gaps remain in the creditor relationship. A high-cost warning is not a finding of illegality.

**Request these two items first:** an itemized platform statement, and proof of payment by the guarantor or a change of creditor if either is claimed to have occurred.

<details>
<summary>What happens when records are incomplete, or a forecast is requested?</summary>

**Incomplete records**

"Two recorded repayments can be verified, but we do not know whether the repayment history is complete. This result covers only the available records; the actual balance cannot yet be confirmed."

**Forecast**

"Show amounts at 1, 3, and 6 months using the charging rules known today. At each date, separate amounts currently due, scheduled amounts not yet due, and the remaining total. Assume no additional repayments; flag unconfirmed guarantee payments, assignments, or charges separately."

**Evidence note**

"Confidence: B, relatively reliable. Weakest component: repayment history. Certainty about the creditor relationship is stated separately."

</details>

## Getting Started

Select **Code > Download ZIP** in this repository and extract the archive. Rename the extracted folder to `debt-cost-checker` and place it in `~/.codex/skills/`. Start a new Codex conversation, attach the records you have, and ask:

```text
Use $debt-cost-checker to break down my current debt,
identify charges that need checking, and estimate the amounts
at 1, 3, and 6 months. Explain the results in Chinese.
```

You can start even if you only remember how much you received and the balance displayed by the platform. Anything that cannot be calculated reliably remains explicitly unconfirmed.

## Scope

| Situation | What the skill provides |
| :--- | :--- |
| Reviewing agreements before borrowing | Known interest and fees, overdue scenarios, and unquantified charges |
| Already overdue | A dated reconstruction of known transactions, with principal, interest, and fees separated |
| Multiple institutions involved | Distinctions between the platform, lender, guarantor, paying guarantor, assignee, and collector |
| Platform balance does not match | A same-date balance comparison and unexplained differences |
| Conflicting records | Preserved sources and discrepancies, with their effect on the result explained |

Calculations currently cover one CNY loan at a time. With an explicit installment schedule, the ledger can record equal-payment, equal-principal, interest-only with principal at maturity, and irregular installments. The quick pre-borrowing simulator currently supports equal-payment amortization only.

**Still requires manual review:** scanned-document recognition, linking agreements, complex compounding, early repayments, refunds and reversals, fee changes after restructuring, and allocating partial guarantee payments or assignments. Unsupported precision is not presented as fact. The output helps reconcile accounts; it does not determine contract validity or whether a debt must be repaid.

## Accuracy and Evidence

- Keep a source for each material amount and rule; distinguish public templates from personally signed documents.
- Check the authenticity of individual transactions separately from the completeness of the repayment history.
- Limit overall calculation confidence by the weakest material evidence. Evidence weights express priority, not a measured accuracy rate.
- Calculate amounts with deterministic scripts and list unknown charges separately.
- Separate currently due amounts, future scheduled amounts, and the remaining total. Apply creditor events by their effective dates.

## Privacy

The calculation scripts run locally and do not initiate network requests. How Codex processes your documents depends on the model and environment you use; the entire workflow is not necessarily offline. Do not upload personal agreements, bank records, or identity information to this public repository, its issues, or comments.

## Chinese-English Terminology

This tool concerns consumer lending in China. The English terms below explain Chinese concepts; they are not presented as official translations or as equivalent rules in other jurisdictions. Applicable rules must be checked against the lender type, contract date, and scope.

| 中文 | English |
| :--- | :--- |
| 综合融资成本 | All-in financing cost |
| 逾期罚息 | Overdue penalty interest |
| 融资担保 / 反担保 | Financing guarantee / counter-guarantee |
| 代偿 / 追偿 | Payment by a guarantor / recovery from the borrower |
| 债权转让 / 受让方 | Assignment of a claim / assignee |
| 提前到期 | Acceleration of repayment obligations |
| 权益包 | Bundled benefits or membership package |
| 贷款市场报价利率（LPR） | Loan Prime Rate (LPR) |
| 民间借贷 | Private lending in the Chinese legal context |
| 司法保护上限 | Upper limit of judicial protection |
| 个人贷款综合融资成本明示表 | Personal loan all-in financing cost disclosure statement |
| 《个人贷款业务明示综合融资成本规定》 | Provisions on Disclosure of All-in Financing Costs for Personal Loan Business |
| 国家金融监督管理总局 / 中国人民银行 | National Financial Regulatory Administration (NFRA) / People's Bank of China (PBOC) |

See [Risk Warnings](references/risk-warnings.md) for review guidance and source links.

<details>
<summary>Technical Notes: Commands, Structure, and Tests</summary>

The scripts require Python 3.10 or later and have no third-party dependencies. After extracting the terms and verifying the structured fields, run:

```bash
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format markdown
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format markdown --detail full
python3 scripts/reconstruct_debt.py /path/to/private-case.json --format json --output result.json
```

Use `scripts/calculate_debt.py` for pre-borrowing equal-payment simulations. See the [input reference](references/input-schema.md) and [JSON Schema](schemas/overdue-case.schema.json) for structured fields.

```text
debt-cost-checker/
|-- README.md         English overview and fictional output
|-- README.zh-CN.md   Complete Chinese overview
|-- SKILL.md          Task instructions and processing principles
|-- agents/           Codex UI metadata
|-- scripts/          Calculations and structured-data redaction
|-- references/       Evidence, creditor relationships, and warnings
|-- schemas/          Structured field definitions
`-- tests/            Calculation and boundary-condition tests
```

```bash
python3 -m unittest discover -s tests -v
```

This is an Alpha version. The 37 automated tests cover calculations and key boundary conditions; end-to-end validation against a complete real-world agreement chain is still pending. All test data is synthetic and contains no borrower's input materials.

</details>
