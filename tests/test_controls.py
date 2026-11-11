# Tests for each control using small hand-built datasets, so the expected result is obvious.

import pandas as pd
import pytest

from billing_audit import controls, generate_data, ingest, pipeline, register


def billing_frame(rows):
    base = {
        "invoice_id": "INV-1", "customer_id": "C1", "customer_name": "Test Co", "billing_date": "2026-10-10",
        "service_code": "FIB-100", "quantity": "1", "unit_price": "899", "amount": "899", "approved_by": "",
    }
    df = pd.DataFrame([{**base, **r} for r in rows]).astype(str)
    df["billing_date_parsed"] = pd.to_datetime(df["billing_date"], format="%Y-%m-%d", errors="coerce")
    df["amount_num"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def ledger_frame(rows):
    df = pd.DataFrame(rows).astype(str)
    df["payment_date_parsed"] = pd.to_datetime(df["payment_date"], errors="coerce")
    df["amount_paid_num"] = pd.to_numeric(df["amount_paid"], errors="coerce")
    return df


def test_invalid_records_are_rejected():
    df = billing_frame([
        {"invoice_id": "A"},
        {"invoice_id": "B", "customer_id": ""},
        {"invoice_id": "C", "billing_date": "2026-13-45"},
        {"invoice_id": "D", "amount": "abc"},
    ])
    valid, invalid = ingest.split_valid(df)
    assert list(valid["invoice_id"]) == ["A"]
    assert set(invalid["invoice_id"]) == {"B", "C", "D"}


def test_duplicate_charge_flagged_once():
    df = billing_frame([{"invoice_id": "INV-1"}, {"invoice_id": "INV-2"}, {"invoice_id": "INV-3", "amount": "500"}])
    found = controls.check_duplicates(df)
    assert len(found) == 1
    assert found[0]["invoice_id"] == "INV-2"
    assert "INV-1" in found[0]["detail"]


def test_repeated_invoice_number_flagged():
    df = billing_frame([{"invoice_id": "INV-1"}, {"invoice_id": "INV-1", "service_code": "SUP-HRS"}])
    found = controls.check_duplicates(df)
    assert any(e["detail"] == "Invoice number appears more than once" for e in found)


def test_threshold_requires_approver():
    df = billing_frame([
        {"invoice_id": "BIG-NO", "amount": "60000"},
        {"invoice_id": "BIG-OK", "amount": "60000", "approved_by": "CFO"},
        {"invoice_id": "EDGE", "amount": "50000"},
    ])
    found = controls.check_approvals(df)
    assert [e["invoice_id"] for e in found] == ["BIG-NO"]


def test_negative_and_zero_amounts():
    df = billing_frame([{"invoice_id": "N", "amount": "-10"}, {"invoice_id": "Z", "amount": "0"},
                        {"invoice_id": "P", "amount": "10"}])
    assert {e["invoice_id"] for e in controls.check_non_positive(df)} == {"N", "Z"}


def test_cutoff_outside_period():
    df = billing_frame([{"invoice_id": "IN"}, {"invoice_id": "LATE", "billing_date": "2026-11-05"},
                        {"invoice_id": "EARLY", "billing_date": "2026-09-30"}])
    assert {e["invoice_id"] for e in controls.check_cutoff(df)} == {"LATE", "EARLY"}


def test_reconciliation_finds_unpaid_short_paid_and_orphans():
    billing = billing_frame([
        {"invoice_id": "PAID", "amount": "100"},
        {"invoice_id": "SHORT", "amount": "100"},
        {"invoice_id": "UNPAID", "amount": "100"},
        {"invoice_id": "ROUNDING", "amount": "100"},
    ])
    ledger = ledger_frame([
        {"payment_reference": "P1", "invoice_id": "PAID", "payment_date": "2026-10-12", "amount_paid": "100"},
        {"payment_reference": "P2", "invoice_id": "SHORT", "payment_date": "2026-10-12", "amount_paid": "90"},
        {"payment_reference": "P3", "invoice_id": "GHOST", "payment_date": "2026-10-12", "amount_paid": "50"},
        {"payment_reference": "P4", "invoice_id": "ROUNDING", "payment_date": "2026-10-12", "amount_paid": "99.995"},
    ])
    found = controls.check_reconciliation(billing, ledger)
    details = {e["invoice_id"]: e["detail"] for e in found}
    assert set(details) == {"SHORT", "UNPAID", "GHOST"}
    assert "difference R10.00" in details["SHORT"]


def test_missing_column_stops_the_audit(tmp_path):
    bad = tmp_path / "billing.csv"
    bad.write_text("invoice_id,amount\nINV-1,100\n")
    with pytest.raises(ingest.SchemaError):
        ingest.load_billing(bad)


def test_register_carries_status_forward_and_closes_fixed_items():
    first = pd.DataFrame([
        {"exception_key": "BC-03|A", "control_id": "BC-03", "control_name": "x", "severity": "High",
         "owner": "Finance", "invoice_id": "A", "customer_id": "C1", "amount": 1, "detail": "d"},
        {"exception_key": "BC-03|B", "control_id": "BC-03", "control_name": "x", "severity": "High",
         "owner": "Finance", "invoice_id": "B", "customer_id": "C1", "amount": 1, "detail": "d"},
    ])
    reg1 = register.update(first, register.load_previous("does-not-exist.csv"))
    assert set(reg1["status"]) == {"Open"}

    # Reviewer marks A as in progress, then B gets fixed at source and disappears from the next run
    reg1.loc[reg1["invoice_id"] == "A", ["status", "resolution_note"]] = ["In Progress", "Approval requested"]
    reg2 = register.update(first[first["invoice_id"] == "A"], reg1.astype(str))

    a = reg2[reg2["invoice_id"] == "A"].iloc[0]
    b = reg2[reg2["invoice_id"] == "B"].iloc[0]
    assert a["status"] == "In Progress"
    assert a["resolution_note"] == "Approval requested"
    assert a["exception_id"] == reg1[reg1["invoice_id"] == "A"].iloc[0]["exception_id"]
    assert b["status"] == "Resolved"


def test_resolved_item_that_reappears_is_reopened():
    current = pd.DataFrame([{"exception_key": "BC-04|A", "control_id": "BC-04", "control_name": "x",
                             "severity": "Medium", "owner": "Finance", "invoice_id": "A", "customer_id": "C1",
                             "amount": -5, "detail": "d"}])
    reg1 = register.update(current, register.load_previous("does-not-exist.csv"))
    reg1["status"] = "Resolved"
    reg2 = register.update(current, reg1.astype(str))
    assert reg2.iloc[0]["status"] == "Open"
    assert "Reopened" in reg2.iloc[0]["resolution_note"]


def test_full_run_finds_every_planted_anomaly(tmp_path):
    _, _, injected = generate_data.write(tmp_path, records=1200, seed=7)
    reg, summary = pipeline.run(tmp_path / "billing_records.csv", tmp_path / "payment_ledger.csv", tmp_path / "out")
    counts = reg.groupby("control_id").size().to_dict()

    assert counts["BC-01"] == injected["invalid_records"]
    assert counts["BC-02"] == injected["duplicate_charges"]
    assert counts["BC-03"] == injected["threshold_breaches"]
    assert counts["BC-04"] == injected["negative_amounts"]
    assert counts["BC-05"] == injected["future_dated"]
    assert counts["BC-06"] == (injected["unpaid_invoices"] + injected["payment_mismatches"]
                               + injected["orphan_payments"])
    assert (tmp_path / "out" / "audit_report.xlsx").exists()
