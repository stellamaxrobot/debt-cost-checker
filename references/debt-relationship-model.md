# Debt Relationship Model

Use this model to explain multi-party online-loan contracts to a user who may recognize only the platform name.

## Roles

| Role | Everyday explanation | Evidence |
| --- | --- | --- |
| `platform` | The app or website where the user applied | registration/service agreement, app screenshot |
| `lender` | The institution that actually advanced the principal | IOU, loan contract, bank credit entry |
| `service_provider` | A party providing referral, technology or post-loan services | service/consulting agreement |
| `guarantor` | A party promising repayment to the lender after defined defaults | guarantee agreement |
| `counter_guarantor` | A party promising to reimburse or protect the guarantor under a separate risk-sharing arrangement | case-specific counter-guarantee agreement, court finding or official disclosure |
| `insurer` | A party providing credit guarantee insurance | policy and insurance authorization |
| `compensating_party` | A guarantor or insurer that actually paid the lender | compensation/subrogation notice and amount |
| `assignee` | A party that acquired the debt or recovery right | assignment notice with effective date |
| `collector` | A party collecting for itself or another creditor | authorization or collection notice; collection alone does not prove ownership |
| `borrower` | The person who received and must account for the loan | identity and signed documents |

## Relationships

Represent each relationship with:

```json
{
  "from": "entity_id",
  "to": "entity_id",
  "type": "funded|serviced|guaranteed|counter_guaranteed|insured|compensated|assigned|collects_for",
  "effective_date": null,
  "amount": null,
  "status": "confirmed|contractual_only|claimed|unknown",
  "source": {"document": "", "clause": "", "date": null}
}
```

Direction conventions:

- `funded`: lender `from` -> borrower `to`;
- `counter_guaranteed`: counter-guarantor `from` -> guarantor `to`;
- `assigned`: previous creditor `from` -> assignee `to`;
- `compensated`: compensating party `from` -> paid creditor `to`; set `subrogation_confirmed: true` only when the materials also establish transfer of the recovery right;
- `collects_for`: collector `from` -> creditor represented `to`.

An effective date is required before a confirmed relationship can change the current-creditor result. Keep an undated notice in the timeline, but do not use it to replace the last confirmed creditor.

Entity names and roles alone establish candidates, not current ownership. For `assigned` and `compensated`, record `scope: full|partial|unknown`. Only a confirmed full-scope change removes the former creditor. Partial/unknown changes retain both parties with an unresolved allocation warning; the engine does not partition the balance between them automatically.

## Event Distinctions

- A guarantee contract proves a guarantee arrangement, not that compensation occurred.
- A counter-guarantee commonly belongs to the institutional cooperation layer, not the borrower's signed package. It does not by itself create a borrower charge, prove compensation or change the current creditor.
- A media report or industry statement that platforms commonly provide counter-guarantees does not prove that a particular loan used that arrangement.
- A compensation clause proves a possible event, not its date or amount.
- An assignment clause proves that assignment is permitted, not that the creditor changed.
- A collection call proves a demand was made, not that the caller owns the debt.
- An app name is not necessarily the lender or current creditor.

## User-Facing Output

Describe the chain chronologically, for example:

```text
The user applied through Platform A. Bank B advanced the principal. Guarantee Company C promised repayment if specified defaults occurred. A current contract permits compensation and assignment, but no compensation or assignment notice has been provided, so Bank B remains the last confirmed creditor.
```

When evidence conflicts, show both claims and name the missing proof instead of choosing one silently.
