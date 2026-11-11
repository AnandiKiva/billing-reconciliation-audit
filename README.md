# Billing Reconciliation and Audit Tool

A Python tool that ingests a month of billing records and a payment ledger, tests them against six automated controls, and produces an audit report and an exception register with resolution tracking.

It replicates the kind of work an IT audit or risk assurance team does when testing a billing process: check the data is complete, test each control, record every exception with an owner, and follow up until it is resolved.

All data is generated mock data. No real customer or financial information is used.

## What it does

1. **Ingests** a billing extract and a payment ledger from CSV, and stops with a clear error if a required column is missing.
2. **Validates** every billing record. Records with missing fields, invalid dates or non-numeric amounts are rejected and logged, instead of being silently skipped.
3. **Tests six controls** across 1,200+ transactions (see the controls matrix below).
4. **Maintains an exception register.** Each exception gets an ID, severity, owner and status. Statuses carry forward between runs.
5. **Reports** results in an Excel workbook for reviewers and a Markdown summary.

## Controls matrix

| ID | Control | Risk addressed | Test performed | Severity | Owner |
|---|---|---|---|---|---|
| BC-01 | Record completeness and validity | Corrupt records are billed incorrectly or not at all | All required fields present, valid date, numeric amount | Medium | Billing Operations |
| BC-02 | Duplicate charge detection | Customers are charged twice | No two invoices share customer, service, amount and date; no repeated invoice numbers | High | Billing Operations |
| BC-03 | High-value approval | Large invoices issued without authorisation | Every invoice above R50,000 has a named approver | High | Finance |
| BC-04 | Negative or zero amounts | Credits processed outside the credit note process | Amount is greater than zero | Medium | Finance |
| BC-05 | Billing cut-off | Revenue recorded in the wrong period | Billing date falls inside the period under review | Medium | Finance |
| BC-06 | Billing to payment reconciliation | Short payments, unpaid invoices, cash with no invoice | Every invoice has a matching payment and every payment links to an invoice | High | Accounts Receivable |

Thresholds and the review period live in `billing_audit/config.py`, so a rule only has to change in one place.

## How to run

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt

# Generate mock data, run the audit, write the reports
python main.py all

# Or run the steps separately
python main.py generate --records 1200 --seed 42
python main.py audit

# Run the tests
python -m pytest
```

## Sample output

Running `python main.py all` with the default seed:

```
Processed 1,223 billing records and 1,197 payments

Open exceptions by control:
  BC-01  Record completeness and validity       10
  BC-02  Duplicate charge detection             15
  BC-03  High-value approval                     8
  BC-04  Negative or zero amounts                6
  BC-05  Billing cut-off                         4
  BC-06  Billing to payment reconciliation      32
```

The generator plants a known number of each anomaly, and the controls find every one of them with no false positives. A test (`test_full_run_finds_every_planted_anomaly`) checks this on a different seed, which is how the controls themselves are validated.

Files written to `output/`:

| File | Purpose |
|---|---|
| `audit_report.xlsx` | Summary with chart, full exception register, controls matrix and rejected records |
| `audit_report.md` | Written report: scope, results per control, resolution status, top exceptions, recommendations |
| `exception_register.csv` | The working register that reviewers update |

## Resolution tracking

The register is designed to be worked on between runs, the same way an audit team follows up findings.

1. Open `output/exception_register.csv` and update the `status` and `resolution_note` columns. Valid statuses are `Open`, `In Progress`, `Resolved` and `Risk Accepted`.
2. Run `python main.py audit` again.

On the next run:

- Statuses, notes and exception IDs are carried forward.
- An exception that is no longer detected is marked `Resolved` automatically, with the date.
- An exception marked `Resolved` that is still detected is **reopened**, because the fix did not work.
- An invalid status value stops the run, so the register cannot drift into inconsistent states.

## Design decisions

- **Everything is read as text first.** Pandas would otherwise guess column types, and one bad value could silently turn an amount column into text or drop leading zeros. Values are converted explicitly, and anything that fails conversion is rejected and reported.
- **Invalid records are excluded from other controls.** A record with no amount cannot be meaningfully tested for duplicates or approval, so it is reported once under BC-01 rather than producing misleading results elsewhere.
- **Duplicates are "possible" duplicates.** Two identical charges on the same day could be a genuine repeat order, so BC-02 flags them for investigation instead of treating them as confirmed errors.
- **A rounding tolerance of R0.01** stops cent-level rounding differences from flooding the register.
- **Reproducible data.** A fixed seed means anyone can regenerate the exact same dataset and re-perform the test.

## Limitations and next steps

- Uses CSV extracts. In practice the data would be pulled directly from the billing system and general ledger, with the extract itself checked for completeness (record counts and control totals agreed to the source).
- Approval is only checked for presence. A stronger test would confirm the approver has the authority for that amount and is not the person who raised the invoice (segregation of duties).
- Could be scheduled to run monthly as a continuous control monitoring job.

## Project structure

```
billing_audit/
  config.py          thresholds, review period, required columns
  generate_data.py   mock data with planted anomalies
  ingest.py          loading, schema check, record validation
  controls.py        the six controls and the controls matrix
  register.py        exception register and resolution tracking
  report.py          Excel and Markdown reports
  pipeline.py        runs the full audit
tests/
  test_controls.py   one test per control plus register and end-to-end tests
main.py              command line entry point
```
