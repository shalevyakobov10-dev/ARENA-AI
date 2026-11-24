# Unified Portfolio Risk Gate

The Polymarket and PERPS engines now share a single **Paper-only entry admission guard**.

## Enforced limits

The guard evaluates the same SQLite ledger used by both engines immediately before any new order is submitted:

- Combined capital allocation: Polymarket open-position cost basis plus PERPS isolated margin in use, capped at `portfolio_risk.max_capital_utilization_pct` of the combined configured starting capital.
- Combined open-position count across both arms.
- Combined current-UTC-day realized PnL plus the current floating PnL of every open Polymarket and PERPS position. Open-position PnL uses the latest persisted executable-side Polymarket bid / mark and PERPS mark-price data; today's open-entry fees and accumulated PERPS funding are included. Closed-trade realized PnL already includes its exit/lifecycle fees. Crossing the combined loss threshold writes the persistent global `halt.json` flag with source `unified-risk`.
- Fail-closed admission: if a ledger snapshot cannot be read, the proposed allocation is invalid, a halt is set or its file is corrupt/unreadable, either configured venue is not in Paper mode, or any open position lacks a fresh and valid mark, new entries are denied. Existing PERPS paper positions remain included in the budget, mark-to-market loss and position count even when the PERPS engine is disabled. Missing/stale marks deny new entries without automatically writing an emergency halt.

## Concurrency

Both automatic entry paths and manual PERPS entries use the same OS-level advisory lock under `PMMB_STATE_DIR/unified-portfolio-entry.lock`. The lock spans the shared-ledger read, admission decision, broker call, and persistence of the resulting fill/position. This serializes cross-arm admissions when Polymarket and PERPS run in separate processes. The operating system releases the lock if a process exits unexpectedly. The production deployment target and CI validation for this PR are Linux. Windows validation is deferred until the existing ARENA-owned runtime module, which imports POSIX `fcntl` unconditionally, is made portable.

## Initial settings

```yaml
portfolio_risk:
  max_capital_utilization_pct: 0.50
  max_open_positions: 8
  max_daily_loss_pct: 0.05
```

With the configured $1,000 Polymarket and $1,000 PERPS starting balances, 50% capital utilization means no more than $1,000 of combined committed capital. Polymarket capital is measured at open cost basis; PERPS capital is measured by isolated margin, not leveraged notional.

## Deliberate limitations

- The guard has no configuration bypass and is hard-coded to Paper mode. Non-Paper execution on either enabled arm is denied.
- The loss stop combines today's realized PnL with the full current floating PnL of open positions. For positions opened before UTC midnight, this is deliberately conservative and is not an exact change-in-unrealized-PnL measurement from midnight; a synchronized start-of-day equity baseline is still a separate improvement.
- Capital utilization is an allocation limit, not a measure of maximum loss.
- Existing open positions are not liquidated by this guard. It denies new entries and persists a global halt after the combined realized daily-loss threshold is crossed.
- The CI gate targets Linux. Windows startup is not currently supported by the existing ARENA-owned runtime module, which imports POSIX `fcntl` unconditionally; this PR does not modify that claimed file.
- The guard is Paper-only. Live trading remains blocked until exchange execution, settlement, recovery, fee accounting, and failure-injection testing are separately validated.
