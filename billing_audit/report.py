# Writes the audit outputs: an Excel workbook for reviewers and a short written report.

from datetime import datetime
from pathlib import Path

import pandas as pd
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from billing_audit import config
from billing_audit.controls import CONTROL_MATRIX

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SEVERITY_FILL = {
    "High": PatternFill("solid", fgColor="F8CBAD"),
    "Medium": PatternFill("solid", fgColor="FFE699"),
    "Low": PatternFill("solid", fgColor="E2EFDA"),
}


def summarise(register, stats):
    controls = pd.DataFrame(CONTROL_MATRIX)[["control_id", "control_name", "severity"]]
    active = register[register["status"] != "Resolved"]
    counts = active.groupby("control_id").size().rename("open_exceptions")
    by_control = controls.merge(counts, on="control_id", how="left").fillna({"open_exceptions": 0})
    by_control["open_exceptions"] = by_control["open_exceptions"].astype(int)
    by_control["result"] = by_control["open_exceptions"].map(lambda n: "Effective" if n == 0 else "Exceptions noted")

    by_status = register.groupby("status").size().reindex(config.VALID_STATUSES, fill_value=0)
    by_severity = active.groupby("severity").size().reindex(["High", "Medium", "Low"], fill_value=0)

    value_at_risk = pd.to_numeric(active["amount"], errors="coerce").abs().sum()
    return {
        "by_control": by_control,
        "by_status": by_status,
        "by_severity": by_severity,
        "value_at_risk": value_at_risk,
        **stats,
    }


def _style_sheet(ws, severity_col=None):
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    ws.freeze_panes = "A2"
    for col in ws.columns:
        width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max(width + 2, 10), 70)
    if severity_col:
        for row in ws.iter_rows(min_row=2):
            sev = row[severity_col - 1].value
            if sev in SEVERITY_FILL:
                row[severity_col - 1].fill = SEVERITY_FILL[sev]


def write_excel(path, register, summary, invalid):
    path = Path(path)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        meta = pd.DataFrame([
            ("Report generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("Period under review", f"{config.PERIOD_START} to {config.PERIOD_END}"),
            ("Billing records ingested", summary["billing_rows"]),
            ("Payment records ingested", summary["ledger_rows"]),
            ("Records failing validation", summary["invalid_rows"]),
            ("Open exceptions", int(summary["by_status"][["Open", "In Progress"]].sum())),
            ("Value of open exceptions (R)", round(summary["value_at_risk"], 2)),
        ], columns=["Item", "Value"])
        meta.to_excel(xw, sheet_name="Summary", index=False)
        summary["by_control"].to_excel(xw, sheet_name="Summary", index=False, startrow=len(meta) + 3)
        status = summary["by_status"].rename_axis("status").reset_index(name="count")
        status_row = len(meta) + len(summary["by_control"]) + 6
        status.to_excel(xw, sheet_name="Summary", index=False, startrow=status_row)

        register.to_excel(xw, sheet_name="Exception Register", index=False)
        pd.DataFrame(CONTROL_MATRIX).to_excel(xw, sheet_name="Controls Matrix", index=False)
        cols = ["invoice_id", "customer_id", "billing_date", "amount", "reason"]
        invalid[cols].to_excel(xw, sheet_name="Rejected Records", index=False)

        wb = xw.book
        _style_sheet(wb["Exception Register"], severity_col=register.columns.get_loc("severity") + 1)
        _style_sheet(wb["Controls Matrix"], severity_col=5)
        _style_sheet(wb["Rejected Records"])

        ws = wb["Summary"]
        ws.cell(row=len(meta) + 1, column=2).number_format = "#,##0.00"
        ws.column_dimensions["A"].width = 32
        ws.column_dimensions["B"].width = 40
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 16
        ws.column_dimensions["E"].width = 18
        for row_idx in (1, len(meta) + 4, status_row + 1):
            for cell in ws[row_idx]:
                if cell.value is not None:
                    cell.fill = HEADER_FILL
                    cell.font = HEADER_FONT

        # Bar chart of open exceptions per control
        table_top = len(meta) + 4
        n = len(summary["by_control"])
        chart = BarChart()
        chart.type = "bar"
        chart.title = "Open exceptions by control"
        chart.legend = None
        data = Reference(ws, min_col=4, min_row=table_top, max_row=table_top + n)
        labels = Reference(ws, min_col=1, min_row=table_top + 1, max_row=table_top + n)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(labels)
        chart.height, chart.width = 8, 16
        ws.add_chart(chart, "G2")


def write_markdown(path, summary, register):
    active = register[register["status"] != "Resolved"]
    lines = [
        "# Billing Reconciliation Audit Report",
        "",
        f"Period under review: {config.PERIOD_START} to {config.PERIOD_END}  ",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Scope",
        "",
        f"- Billing records ingested: {summary['billing_rows']:,}",
        f"- Payment records ingested: {summary['ledger_rows']:,}",
        f"- Records rejected at validation: {summary['invalid_rows']:,}",
        "",
        "## Results by control",
        "",
        "| Control | Name | Severity | Open exceptions | Result |",
        "|---|---|---|---|---|",
    ]
    for r in summary["by_control"].itertuples(index=False):
        lines.append(f"| {r.control_id} | {r.control_name} | {r.severity} | {r.open_exceptions} | {r.result} |")

    lines += [
        "",
        "## Resolution status",
        "",
        "| Status | Count |",
        "|---|---|",
    ]
    for status, count in summary["by_status"].items():
        lines.append(f"| {status} | {count} |")

    lines += [
        "",
        f"Total value of open exceptions: R{summary['value_at_risk']:,.2f}",
        "",
        "## Highest value open exceptions",
        "",
        "| ID | Control | Invoice | Amount (R) | Detail |",
        "|---|---|---|---|---|",
    ]
    top = active.assign(abs_amount=pd.to_numeric(active["amount"], errors="coerce").abs())
    for r in top.sort_values("abs_amount", ascending=False).head(10).itertuples(index=False):
        amt = f"{r.abs_amount:,.2f}" if pd.notna(r.abs_amount) else "n/a"
        lines.append(f"| {r.exception_id} | {r.control_id} | {r.invoice_id} | {amt} | {r.detail} |")

    lines += [
        "",
        "## Recommendations",
        "",
        "1. Billing Operations to investigate BC-02 duplicates and issue credit notes where customers were double charged.",
        "2. Finance to obtain retrospective approval for BC-03 items and confirm the approval workflow blocks unapproved high-value invoices.",
        "3. Accounts Receivable to follow up BC-06 short payments and allocate or refund payments with no matching invoice.",
        "4. Fix the source of BC-01 rejected records so invalid data cannot be captured in the billing system.",
        "",
    ]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
