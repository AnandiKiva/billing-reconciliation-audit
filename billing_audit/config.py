# Audit parameters used by every control.
# Changing a value here changes the rule everywhere, which keeps the controls consistent and easy to review.

from datetime import date

# Billing period under review
PERIOD_START = date(2026, 10, 1)
PERIOD_END = date(2026, 10, 31)

# Any single invoice above this amount (ZAR) must have a named approver
APPROVAL_THRESHOLD = 50_000.00

# Billed vs paid differences smaller than this are treated as rounding, not exceptions
AMOUNT_TOLERANCE = 0.01

# Columns the billing extract must contain before any control can run
BILLING_COLUMNS = [
    "invoice_id",
    "customer_id",
    "customer_name",
    "billing_date",
    "service_code",
    "quantity",
    "unit_price",
    "amount",
    "approved_by",
]

LEDGER_COLUMNS = [
    "payment_reference",
    "invoice_id",
    "payment_date",
    "amount_paid",
]

# Fields that may never be blank on a billing record
REQUIRED_BILLING_FIELDS = ["invoice_id", "customer_id", "billing_date", "service_code", "amount"]

# Statuses an exception can have in the register
VALID_STATUSES = ["Open", "In Progress", "Resolved", "Risk Accepted"]
