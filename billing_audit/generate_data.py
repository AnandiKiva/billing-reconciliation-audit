# Generates mock billing and payment data for one billing period.
# Known anomalies are injected on purpose so the controls have something real to find.
# A seed makes every run reproducible, which matters when you want to re-perform a test.

import random
from datetime import timedelta
from pathlib import Path

import pandas as pd

from billing_audit import config

SERVICES = {
    "FIB-100": ("Fibre 100Mbps line", 899.00),
    "FIB-500": ("Fibre 500Mbps line", 1_499.00),
    "CLD-STD": ("Cloud hosting standard", 2_350.00),
    "CLD-ENT": ("Cloud hosting enterprise", 8_900.00),
    "SEC-MON": ("Managed security monitoring", 12_500.00),
    "LIC-365": ("Office licence bundle", 245.00),
    "SUP-HRS": ("Support hours", 650.00),
}

COMPANY_WORDS_A = ["Ubuntu", "Highveld", "Karoo", "Protea", "Baobab", "Lekker", "Sable", "Jacaranda",
                   "Kgalagadi", "Drakensberg", "Mzansi", "Indlovu", "Thaba", "Limpopo", "Kudu"]
COMPANY_WORDS_B = ["Logistics", "Holdings", "Foods", "Engineering", "Consulting", "Retail",
                   "Medical", "Mining Services", "Properties", "Transport", "Media", "Agri"]

APPROVERS = ["T. Mokoena (Finance Manager)", "R. Naidoo (Financial Controller)", "L. van Wyk (CFO)"]


def _make_customers(rng, count=120):
    customers = []
    used = set()
    while len(customers) < count:
        name = f"{rng.choice(COMPANY_WORDS_A)} {rng.choice(COMPANY_WORDS_B)} (Pty) Ltd"
        if name in used:
            continue
        used.add(name)
        customers.append((f"CUST-{len(customers) + 1:04d}", name))
    return customers


def _random_period_date(rng):
    days = (config.PERIOD_END - config.PERIOD_START).days
    return config.PERIOD_START + timedelta(days=rng.randint(0, days))


def generate(records=1200, seed=42):
    # Returns (billing_df, ledger_df, injected) where injected counts each planted anomaly
    rng = random.Random(seed)
    customers = _make_customers(rng)
    rows = []
    seen = set()

    for i in range(records):
        # Redraw if the random charge happens to match an earlier one, so the only duplicates are the planted ones
        while True:
            customer_id, customer_name = rng.choice(customers)
            code = rng.choice(list(SERVICES))
            unit_price = SERVICES[code][1]
            # Most invoices are small, a few large enterprise orders cross the approval threshold
            quantity = rng.randint(30, 60) if rng.random() < 0.04 else rng.randint(1, 12)
            bill_date = _random_period_date(rng).isoformat()
            if (customer_id, code, quantity, bill_date) not in seen:
                seen.add((customer_id, code, quantity, bill_date))
                break
        amount = round(unit_price * quantity, 2)
        approver = rng.choice(APPROVERS) if amount > config.APPROVAL_THRESHOLD else ""
        rows.append({
            "invoice_id": f"INV-2026-{i + 1:05d}",
            "customer_id": customer_id,
            "customer_name": customer_name,
            "billing_date": bill_date,
            "service_code": code,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
            "approved_by": approver,
        })

    billing = pd.DataFrame(rows)
    injected = {}
    next_id = records + 1

    # Duplicate charges: same customer, service, amount and date billed twice under a new invoice number
    dup_sources = rng.sample(range(len(billing)), 15)
    dup_rows = []
    for idx in dup_sources:
        row = billing.iloc[idx].to_dict()
        row["invoice_id"] = f"INV-2026-{next_id:05d}"
        next_id += 1
        dup_rows.append(row)
    billing = pd.concat([billing, pd.DataFrame(dup_rows)], ignore_index=True)
    injected["duplicate_charges"] = len(dup_rows)

    # Threshold breaches: large invoices with the approval removed
    breach_rows = []
    for _ in range(8):
        customer_id, customer_name = rng.choice(customers)
        quantity = rng.randint(5, 9)
        breach_rows.append({
            "invoice_id": f"INV-2026-{next_id:05d}",
            "customer_id": customer_id,
            "customer_name": customer_name,
            "billing_date": _random_period_date(rng).isoformat(),
            "service_code": "SEC-MON",
            "quantity": quantity,
            "unit_price": 12_500.00,
            "amount": round(12_500.00 * quantity, 2),
            "approved_by": "",
        })
        next_id += 1
    billing = pd.concat([billing, pd.DataFrame(breach_rows)], ignore_index=True)
    injected["threshold_breaches"] = len(breach_rows)

    # Pick rows to corrupt from the original block only, so injections do not overlap
    corrupt_pool = [i for i in range(records) if i not in dup_sources]
    rng.shuffle(corrupt_pool)

    # Negative amounts with no credit note
    for idx in corrupt_pool[:6]:
        billing.at[idx, "amount"] = -abs(billing.at[idx, "amount"])
    injected["negative_amounts"] = 6

    # Invalid or incomplete records
    # The amount column becomes text here because real extracts can contain non-numeric values
    billing["amount"] = billing["amount"].astype(object)
    invalid_targets = corrupt_pool[6:16]
    for n, idx in enumerate(invalid_targets):
        kind = n % 3
        if kind == 0:
            billing.at[idx, "customer_id"] = ""
        elif kind == 1:
            billing.at[idx, "billing_date"] = "2026-13-45"
        else:
            billing.at[idx, "amount"] = "abc"
    injected["invalid_records"] = len(invalid_targets)

    # Invoices dated after the period end
    for idx in corrupt_pool[16:20]:
        future = config.PERIOD_END + timedelta(days=rng.randint(3, 20))
        billing.at[idx, "billing_date"] = future.isoformat()
    injected["future_dated"] = 4

    # Build the payment ledger, then plant reconciliation problems
    invalid_ids = set(billing.loc[invalid_targets, "invoice_id"])
    payable = billing[~billing["invoice_id"].isin(invalid_ids)].copy()
    payable["amount"] = pd.to_numeric(payable["amount"])
    payable = payable[payable["amount"] > 0]

    unpaid_ids = set(rng.sample(list(payable["invoice_id"]), 15))
    mismatch_ids = set(rng.sample([x for x in payable["invoice_id"] if x not in unpaid_ids], 12))

    ledger_rows = []
    for n, row in enumerate(payable.itertuples(index=False)):
        if row.invoice_id in unpaid_ids:
            continue
        paid = row.amount
        if row.invoice_id in mismatch_ids:
            paid = round(paid - rng.choice([100.00, 250.00, 899.00, 1_000.00]), 2)
        bill_date = pd.Timestamp(row.billing_date).date()
        ledger_rows.append({
            "payment_reference": f"PAY-{n + 1:06d}",
            "invoice_id": row.invoice_id,
            "payment_date": (bill_date + timedelta(days=rng.randint(1, 25))).isoformat(),
            "amount_paid": paid,
        })

    # Payments that point at invoices which do not exist
    for k in range(5):
        ledger_rows.append({
            "payment_reference": f"PAY-X{k + 1:05d}",
            "invoice_id": f"INV-2026-9{k + 1:04d}",
            "payment_date": _random_period_date(rng).isoformat(),
            "amount_paid": round(rng.uniform(500, 9_000), 2),
        })

    ledger = pd.DataFrame(ledger_rows)
    injected["unpaid_invoices"] = len(unpaid_ids)
    injected["payment_mismatches"] = len(mismatch_ids)
    injected["orphan_payments"] = 5

    # Shuffle so anomalies are not all at the bottom of the file
    billing = billing.sample(frac=1, random_state=seed).reset_index(drop=True)
    ledger = ledger.sample(frac=1, random_state=seed).reset_index(drop=True)
    return billing, ledger, injected


def write(out_dir="data", records=1200, seed=42):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    billing, ledger, injected = generate(records, seed)
    billing.to_csv(out / "billing_records.csv", index=False)
    ledger.to_csv(out / "payment_ledger.csv", index=False)
    return billing, ledger, injected
