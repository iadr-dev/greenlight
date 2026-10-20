"""Late fees on overdue balances. Money is whole cents everywhere."""
from __future__ import annotations

GRACE_DAYS = 14
PERIOD_DAYS = 30
FEE_PERCENT_PER_PERIOD = 2
MAX_PERIODS = 3
WRITE_OFF_DAYS = 90


def late_fee(balance_cents: int, days_overdue: int) -> int:
    """The fee for a balance that is ``days_overdue`` days past due.

    Nothing during the 14 days of grace; then 2% of the balance for every started 30-day period, at most three.
    """
    if balance_cents < 0 or days_overdue < 0:
        raise ValueError("balance and days overdue must not be negative")
    if days_overdue <= GRACE_DAYS:
        return 0
    if days_overdue > WRITE_OFF_DAYS:
        return 0
    periods = min(MAX_PERIODS, -(-(days_overdue - GRACE_DAYS) // PERIOD_DAYS))
    return balance_cents * FEE_PERCENT_PER_PERIOD * periods // 100
