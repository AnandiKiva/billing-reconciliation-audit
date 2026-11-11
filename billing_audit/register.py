# Exception register with resolution tracking.
# Statuses and notes from the previous run are carried forward, so follow-up work is never lost between runs.
# Exceptions that were open last time but are no longer detected are marked as resolved automatically.

from datetime import date
from pathlib import Path

import pandas as pd

from billing_audit import config

REGISTER_COLUMNS = [
    "exception_id", "exception_key", "control_id", "control_name", "severity", "owner",
    "invoice_id", "customer_id", "amount", "detail",
    "status", "first_detected", "last_detected", "resolution_note",
]


def load_previous(path):
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=REGISTER_COLUMNS)
    prev = pd.read_csv(path, dtype=str, keep_default_na=False)
    bad = set(prev["status"]) - set(config.VALID_STATUSES)
    if bad:
        raise ValueError(f"Unknown status values in register: {', '.join(sorted(bad))}. "
                         f"Use one of: {', '.join(config.VALID_STATUSES)}")
    return prev


def update(current, previous, run_date=None):
    run_date = (run_date or date.today()).isoformat()
    prev = previous.set_index("exception_key") if len(previous) else None
    rows = []

    for r in current.to_dict("records"):
        key = r["exception_key"]
        if prev is not None and key in prev.index:
            old = prev.loc[key]
            r["exception_id"] = old["exception_id"]
            r["status"] = old["status"]
            r["first_detected"] = old["first_detected"]
            r["resolution_note"] = old["resolution_note"]
            # An item marked resolved that shows up again was not really fixed
            if old["status"] == "Resolved":
                r["status"] = "Open"
                r["resolution_note"] = f"Reopened {run_date}: still detected. {old['resolution_note']}".strip()
        else:
            r["exception_id"] = ""
            r["status"] = "Open"
            r["first_detected"] = run_date
            r["resolution_note"] = ""
        r["last_detected"] = run_date
        rows.append(r)

    if prev is not None:
        current_keys = set(current["exception_key"])
        for key, old in prev.iterrows():
            if key in current_keys:
                continue
            carried = old.to_dict()
            carried["exception_key"] = key
            if carried["status"] in ("Open", "In Progress"):
                carried["status"] = "Resolved"
                note = carried.get("resolution_note", "")
                carried["resolution_note"] = f"No longer detected on {run_date}. {note}".strip()
            rows.append(carried)

    register = pd.DataFrame(rows, columns=REGISTER_COLUMNS)
    register = register.sort_values(["control_id", "invoice_id", "exception_key"]).reset_index(drop=True)

    # Existing exceptions keep their ID so they can be referenced in follow-up emails and reports
    existing = [int(x.split("-")[1]) for x in register["exception_id"] if x]
    next_num = max(existing, default=0) + 1
    for i in register.index:
        if not register.at[i, "exception_id"]:
            register.at[i, "exception_id"] = f"EX-{next_num:04d}"
            next_num += 1
    return register
