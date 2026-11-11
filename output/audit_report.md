# Billing Reconciliation Audit Report

Period under review: 2026-10-01 to 2026-10-31  
Generated: 2026-11-11 22:08

## Scope

- Billing records ingested: 1,223
- Payment records ingested: 1,197
- Records rejected at validation: 10

## Results by control

| Control | Name | Severity | Open exceptions | Result |
|---|---|---|---|---|
| BC-01 | Record completeness and validity | Medium | 10 | Exceptions noted |
| BC-02 | Duplicate charge detection | High | 15 | Exceptions noted |
| BC-03 | High-value approval | High | 8 | Exceptions noted |
| BC-04 | Negative or zero amounts | Medium | 6 | Exceptions noted |
| BC-05 | Billing cut-off | Medium | 4 | Exceptions noted |
| BC-06 | Billing to payment reconciliation | High | 32 | Exceptions noted |

## Resolution status

| Status | Count |
|---|---|
| Open | 75 |
| In Progress | 0 |
| Resolved | 0 |
| Risk Accepted | 0 |

Total value of open exceptions: R2,661,125.23

## Highest value open exceptions

| ID | Control | Invoice | Amount (R) | Detail |
|---|---|---|---|---|
| EX-0062 | BC-06 | INV-2026-00848 | 338,200.00 | No payment found for this invoice |
| EX-0033 | BC-03 | INV-2026-01223 | 112,500.00 | R112,500.00 exceeds the R50,000 threshold with no approver |
| EX-0027 | BC-03 | INV-2026-01217 | 112,500.00 | R112,500.00 exceeds the R50,000 threshold with no approver |
| EX-0023 | BC-02 | INV-2026-01213 | 112,500.00 | Possible duplicate of INV-2026-01105 (same customer, service, amount and date) |
| EX-0026 | BC-03 | INV-2026-01216 | 112,500.00 | R112,500.00 exceeds the R50,000 threshold with no approver |
| EX-0070 | BC-06 | INV-2026-01221 | 100,000.00 | Billed R100,000.00, paid R99,750.00 (difference R250.00) |
| EX-0031 | BC-03 | INV-2026-01221 | 100,000.00 | R100,000.00 exceeds the R50,000 threshold with no approver |
| EX-0047 | BC-06 | INV-2026-00166 | 100,000.00 | No payment found for this invoice |
| EX-0030 | BC-03 | INV-2026-01220 | 100,000.00 | R100,000.00 exceeds the R50,000 threshold with no approver |
| EX-0015 | BC-02 | INV-2026-01205 | 97,900.00 | Possible duplicate of INV-2026-00667 (same customer, service, amount and date) |

## Recommendations

1. Billing Operations to investigate BC-02 duplicates and issue credit notes where customers were double charged.
2. Finance to obtain retrospective approval for BC-03 items and confirm the approval workflow blocks unapproved high-value invoices.
3. Accounts Receivable to follow up BC-06 short payments and allocate or refund payments with no matching invoice.
4. Fix the source of BC-01 rejected records so invalid data cannot be captured in the billing system.
