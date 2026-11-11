# Loads the extracts and checks they are fit to audit.
# Everything is read as text first so a bad value cannot silently change a column's type.

from pathlib import Path

import pandas as pd

from billing_audit import config


class SchemaError(Exception):
    pass


def _check_columns(df, expected, name):
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing required columns: {', '.join(missing)}")


def load_billing(path):
    df = pd.read_csv(Path(path), dtype=str, keep_default_na=False)
    _check_columns(df, config.BILLING_COLUMNS, "Billing extract")
    df = df.apply(lambda col: col.str.strip())
    df["billing_date_parsed"] = pd.to_datetime(df["billing_date"], format="%Y-%m-%d", errors="coerce")
    df["amount_num"] = pd.to_numeric(df["amount"], errors="coerce")
    return df


def load_ledger(path):
    df = pd.read_csv(Path(path), dtype=str, keep_default_na=False)
    _check_columns(df, config.LEDGER_COLUMNS, "Payment ledger")
    df = df.apply(lambda col: col.str.strip())
    df["payment_date_parsed"] = pd.to_datetime(df["payment_date"], format="%Y-%m-%d", errors="coerce")
    df["amount_paid_num"] = pd.to_numeric(df["amount_paid"], errors="coerce")
    return df


def split_valid(billing):
    # Returns (valid_rows, invalid_rows) where invalid_rows has a reason column
    reasons = pd.Series("", index=billing.index)

    for field in config.REQUIRED_BILLING_FIELDS:
        blank = billing[field] == ""
        reasons[blank] += f"Missing {field}; "

    bad_date = (billing["billing_date"] != "") & billing["billing_date_parsed"].isna()
    reasons[bad_date] += "Invalid billing_date; "

    bad_amount = (billing["amount"] != "") & billing["amount_num"].isna()
    reasons[bad_amount] += "Non-numeric amount; "

    invalid_mask = reasons != ""
    invalid = billing[invalid_mask].copy()
    invalid["reason"] = reasons[invalid_mask].str.rstrip("; ")
    return billing[~invalid_mask].copy(), invalid
