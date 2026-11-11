# Runs the full audit: ingest, validate, test controls, update the register, write reports.

from pathlib import Path

from billing_audit import controls, ingest, register, report


def run(billing_path, ledger_path, out_dir="output", run_date=None):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    billing = ingest.load_billing(billing_path)
    ledger = ingest.load_ledger(ledger_path)
    valid, invalid = ingest.split_valid(billing)

    exceptions = controls.run_all(valid, invalid, ledger)

    register_path = out / "exception_register.csv"
    previous = register.load_previous(register_path)
    reg = register.update(exceptions, previous, run_date)
    reg.to_csv(register_path, index=False)

    stats = {"billing_rows": len(billing), "ledger_rows": len(ledger), "invalid_rows": len(invalid)}
    summary = report.summarise(reg, stats)
    report.write_excel(out / "audit_report.xlsx", reg, summary, invalid)
    report.write_markdown(out / "audit_report.md", summary, reg)
    return reg, summary
