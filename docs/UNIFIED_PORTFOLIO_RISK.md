# Unified Portfolio Risk Gate

The Polymarket and PERPS engines now share a single **Paper-only entry admission guard**.

## Enforced limits

The guard evaluates the same SQLite ledger used by both engines immediately before any new order is submitted:

- Combined capital allocation: Polymarket open-position cost basis plus PERPS isolated margin in use, capped at `portfolio_risk.max_capital_utilization_pct` of the combined configured starting capital.
- Combined open-position count across both arms.
- Combined realized PnL for the current UTC day, summing the Polymarket fills ledger and PERPS fills ledger. Crossing the daily threshold writes the persistent global `halt.json` flag with source `unified-risk`.
- Fail-closed admission: if a ledger snapshot cannot be read, the proposed allocation is invalid, the global halt is set, or an enabled arm is not in Paper mode, new entries are denied.

## Concurrency

Both automatic entry paths and manual PERPS entries use the same OS-level advisory lock under `PMMB_STATE_DIR/unified-portfolio-entry.lock`. The lock spans the shared-ledger read, admission decision, broker call, and persistence of the resulting fill/position. This serializes cross-arm admissions when Polymarket and PERPS run in separate processes. The operating system releases the lock if a process exits unexpectedly.

## Initial settings

```yaml
portfolio_risk:
  enabled: true
  paper_only: true
  max_capital_utilization_pct: 0.50
  max_open_positions: 8
  max_daily_loss_pct: 0.05
```

With the configured $1,000 Polymarket and $1,000 PERPS starting balances, 50% capital utilization means no more than $1,000 of combined committed capital. Polymarket capital is measured at open cost basis; PERPS capital is measured by isolated margin, not leveraged notional.

## Deliberate limitations

- The daily stop uses realized PnL in the two ledgers; it does not yet calculate a synchronized combined intraday mark-to-market drawdown.
- Capital utilization is an allocation limit, not a measure of maximum loss.
- Existing open positions are not liquidated by this guard. It denies new entries and persists a global halt after the combined realized daily-loss threshold is crossed.
- The guard is Paper-only. Live trading remains blocked until exchange execution, settlement, recovery, fee accounting, and failure-injection testing are separately validated.
