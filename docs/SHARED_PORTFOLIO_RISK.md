# Shared portfolio risk budget

The Polymarket and PERPS engines share one SQLite-backed allocation gate before sending an entry.

## What is counted

- Polymarket: open position cost basis (shares multiplied by average entry price).
- PERPS: isolated margin committed, not gross leveraged notional.
- In-flight reservations: capital reserved by either engine but not yet persisted as an open position.

The default cap is 50% of configured starting capital for the execution mode. When both arms use the same mode, their configured starting cash is added. Paper and live budgets are isolated. The default combined open-position cap is eight.

## Atomicity and failure behavior

Reservations are inserted under SQLite BEGIN IMMEDIATE, so concurrent processes cannot both spend the same remaining budget. Each engine reserves before calling its broker. A no-fill releases the reservation; a successful entry releases it only after the position is persisted. If the process fails after a fill but before persistence, the reservation remains and blocks further entries (fail-closed). Review the shared_risk_reservations table during recovery; do not delete a reservation until broker/fill reconciliation confirms there is no unrecorded position.

If the shared-risk database read or write fails, new entries are rejected. Existing positions can still be monitored and closed.

## Scope and limitations

This is a capital-allocation guard, not yet a complete shared portfolio risk model. It does not aggregate cross-venue daily realized loss, peak-equity drawdown, correlated factor exposure, funding stress, or liquidation stress. PERPS allocation uses margin because leveraged notional is not equivalent to cash committed. Configure shared_risk.enabled, shared_risk.max_allocation_pct, and shared_risk.max_open_positions in YAML. Defaults: enabled, 50%, and eight positions.

This change does not enable live trading, add credentials, or send live orders.
