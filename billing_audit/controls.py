# The automated controls.
# Each control answers one audit question and returns a list of exceptions.
# CONTROL_MATRIX documents every control the same way an auditor would in a controls matrix.

import pandas as pd

from billing_audit import config

CONTROL_MATRIX = [
    {
        "control_id": "BC-01",
        "control_name": "Record completeness and validity",
        "risk": "Incomplete or corrupt records are billed incorrectly or not at all",
        "test": "Every billing record has all required fields, a valid date and a numeric amount",
        "severity": "Medium",
        "owner": "Billing Operations",
    },
    {
        "control_id": "BC-02",
        "control_name": "Duplicate charge detection",
        "risk": "Customers are charged twice for the same service, causing refunds and reputational damage",
        "test": "No two invoices share the same customer, service, amount and billing date, and no invoice number repeats",
        "severity": "High",
        "owner": "Billing Operations",
    },
    {
        "control_id": "BC-03",
        "control_name": "High-value approval",
        "risk": "Large invoices are issued without management authorisation",
        "test": f"Every invoice above R{config.APPROVAL_THRESHOLD:,.0f} has a named approver",
        "severity": "High",
        "owner": "Finance",
    },
    {
        "control_id": "BC-04",
        "control_name": "Negative or zero amounts",
        "risk": "Credits are processed outside the credit note process, hiding revenue leakage",
        "test": "Billing records have an amount greater than zero",
        "severity": "Medium",
        "owner": "Finance",
    },
    {
        "control_id": "BC-05",
        "control_name": "Billing cut-off",
        "risk": "Revenue is recorded in the wrong period",
        "test": "Billing date falls inside the period under review",
        "severity": "Medium",
        "owner": "Finance",
    },
    {
        "control_id": "BC-06",
        "control_name": "Billing to payment reconciliation",
        "risk": "Payments do not match what was billed, or cash is received with no supporting invoice",
        "test": "Every valid invoice has a payment for the same amount and every payment links to an invoice",
        "severity": "High",
        "owner": "Accounts Receivable",
    },
]

_META = {c["control_id"]: c for c in CONTROL_MATRIX}


def _exception(control_id, detail, invoice_id="", customer_id="", amount=None, reference="", severity=None):
    meta = _META[control_id]
    key_ref = reference or invoice_id
    return {
        "exception_key": f"{control_id}|{key_ref}",
        "control_id": control_id,
        "control_name": meta["control_name"],
        "severity": severity or meta["severity"],
        "owner": meta["owner"],
        "invoice_id": invoice_id,
        "customer_id": customer_id,
        "amount": amount,
        "detail": detail,
    }


def check_validity(invalid_rows):
    return [
        _exception("BC-01", r.reason, r.invoice_id, r.customer_id, None)
        for r in invalid_rows.itertuples(index=False)
    ]


def check_duplicates(billing):
    found = []

    # Same invoice number used more than once
    repeated = billing[billing.duplicated("invoice_id", keep="first")]
    for r in repeated.itertuples(index=False):
        found.append(_exception("BC-02", "Invoice number appears more than once",
                                r.invoice_id, r.customer_id, r.amount_num,
                                reference=f"{r.invoice_id}-repeat"))

    # Same charge raised under different invoice numbers
    key = ["customer_id", "service_code", "amount_num", "billing_date"]
    ordered = billing.sort_values("invoice_id")
    first_seen = ordered.drop_duplicates(subset=key, keep="first").set_index(key)["invoice_id"]
    dupes = ordered[ordered.duplicated(subset=key, keep="first")]
    for r in dupes.itertuples(index=False):
        original = first_seen.loc[(r.customer_id, r.service_code, r.amount_num, r.billing_date)]
        found.append(_exception("BC-02", f"Possible duplicate of {original} (same customer, service, amount and date)",
                                r.invoice_id, r.customer_id, r.amount_num))
    return found


def check_approvals(billing):
    over = billing[(billing["amount_num"] > config.APPROVAL_THRESHOLD) & (billing["approved_by"] == "")]
    return [
        _exception("BC-03",
                   f"R{r.amount_num:,.2f} exceeds the R{config.APPROVAL_THRESHOLD:,.0f} threshold with no approver",
                   r.invoice_id, r.customer_id, r.amount_num)
        for r in over.itertuples(index=False)
    ]


def check_non_positive(billing):
    bad = billing[billing["amount_num"] <= 0]
    return [
        _exception("BC-04", "Amount is zero or negative with no credit note reference",
                   r.invoice_id, r.customer_id, r.amount_num)
        for r in bad.itertuples(index=False)
    ]


def check_cutoff(billing):
    start = pd.Timestamp(config.PERIOD_START)
    end = pd.Timestamp(config.PERIOD_END)
    outside = billing[(billing["billing_date_parsed"] < start) | (billing["billing_date_parsed"] > end)]
    return [
        _exception("BC-05",
                   f"Billed on {r.billing_date}, outside period {config.PERIOD_START} to {config.PERIOD_END}",
                   r.invoice_id, r.customer_id, r.amount_num)
        for r in outside.itertuples(index=False)
    ]


def check_reconciliation(billing, ledger):
    found = []
    billable = billing[billing["amount_num"] > 0].drop_duplicates("invoice_id")
    paid = ledger.groupby("invoice_id", as_index=False)["amount_paid_num"].sum()
    merged = billable.merge(paid, on="invoice_id", how="left")

    unpaid = merged[merged["amount_paid_num"].isna()]
    for r in unpaid.itertuples(index=False):
        found.append(_exception("BC-06", "No payment found for this invoice",
                                r.invoice_id, r.customer_id, r.amount_num, severity="Medium"))

    matched = merged[merged["amount_paid_num"].notna()]
    diff = (matched["amount_num"] - matched["amount_paid_num"]).abs()
    mismatched = matched[diff > config.AMOUNT_TOLERANCE]
    for r in mismatched.itertuples(index=False):
        gap = r.amount_num - r.amount_paid_num
        found.append(_exception("BC-06",
                                f"Billed R{r.amount_num:,.2f}, paid R{r.amount_paid_num:,.2f} (difference R{gap:,.2f})",
                                r.invoice_id, r.customer_id, r.amount_num))

    known = set(billing["invoice_id"])
    orphans = ledger[~ledger["invoice_id"].isin(known)]
    for r in orphans.itertuples(index=False):
        found.append(_exception("BC-06", f"Payment {r.payment_reference} references unknown invoice {r.invoice_id}",
                                r.invoice_id, "", r.amount_paid_num, reference=r.payment_reference))
    return found


def run_all(valid_billing, invalid_billing, ledger):
    exceptions = []
    exceptions += check_validity(invalid_billing)
    exceptions += check_duplicates(valid_billing)
    exceptions += check_approvals(valid_billing)
    exceptions += check_non_positive(valid_billing)
    exceptions += check_cutoff(valid_billing)
    exceptions += check_reconciliation(valid_billing, ledger)
    return pd.DataFrame(exceptions, columns=[
        "exception_key", "control_id", "control_name", "severity", "owner",
        "invoice_id", "customer_id", "amount", "detail",
    ])
