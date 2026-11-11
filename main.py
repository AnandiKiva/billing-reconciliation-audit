# Command line entry point.
#   python main.py generate     create mock data in data/
#   python main.py audit        run the controls and write reports to output/
#   python main.py all          both of the above

import argparse
import sys

from billing_audit import generate_data, pipeline
from billing_audit.ingest import SchemaError


def cmd_generate(args):
    billing, ledger, injected = generate_data.write(args.data_dir, args.records, args.seed)
    print(f"Wrote {len(billing):,} billing records and {len(ledger):,} payments to {args.data_dir}/")
    print("Anomalies planted:")
    for name, count in injected.items():
        print(f"  {name}: {count}")


def cmd_audit(args):
    try:
        reg, summary = pipeline.run(f"{args.data_dir}/billing_records.csv",
                                    f"{args.data_dir}/payment_ledger.csv", args.out_dir)
    except (SchemaError, FileNotFoundError, ValueError) as err:
        print(f"Audit stopped: {err}")
        sys.exit(1)

    print(f"Processed {summary['billing_rows']:,} billing records and {summary['ledger_rows']:,} payments")
    print("\nOpen exceptions by control:")
    for r in summary["by_control"].itertuples(index=False):
        print(f"  {r.control_id}  {r.control_name:<36} {r.open_exceptions:>4}")
    print("\nResolution status:")
    for status, count in summary["by_status"].items():
        print(f"  {status:<14} {count:>4}")
    print(f"\nValue of open exceptions: R{summary['value_at_risk']:,.2f}")
    print(f"Reports written to {args.out_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Billing reconciliation and audit tool")
    parser.add_argument("command", choices=["generate", "audit", "all"])
    parser.add_argument("--records", type=int, default=1200, help="number of base invoices to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed for reproducible data")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default="output")
    args = parser.parse_args()

    if args.command in ("generate", "all"):
        cmd_generate(args)
    if args.command in ("audit", "all"):
        if args.command == "all":
            print()
        cmd_audit(args)


if __name__ == "__main__":
    main()
