# Unified Portfolio Risk Gate

The Polymarket and PERPS engines now share a single **Paper-only entry admission guard**.

## Enforced limits

The guard evaluates the same SQLite ledger used by both engines immediately before any new order is submitted:

- Combined capital allocation: Polymarket open-position cost basis plus PERPS isolated margin in use, capped at `portfolio_risk.max_capital_utilization_pct` of the combined configured starting capital.
- Combined open-position count across both arms.
- Daily loss is the change in realized plus floating PnL from one immutable synchronized UTC baseline: `(realized_today - baseline_realized) + (current_unrealized - baseline_unrealized)`. Baselines are stored in the additive `unified_day_baselines` SQLite table and inserted once per UTC date; concurrent engine processes read back the winning insert. For existing open positions, capture requires fresh marks with no more than 120 seconds cross-venue timestamp skew, and marks no older than 120 seconds before UTC midnight. Both engines capture under the shared OS lock before exits or entries. Today’s open-entry fees and accumulated PERPS funding are included; prior-day PERPS entry fees allocated into today’s partial/complete close are added back so historical fees are not double-counted as today’s loss. Crossing the combined loss threshold writes the persistent global `halt.json` flag with source `unified-risk`.
- Paper-ledger isolation: the unified guard always reads the Polymarket Paper ledger and the PERPS Paper ledger. Existing Paper PERPS positions remain included even when the PERPS engine is disabled. A disabled PERPS arm configured for Live does not mix its separate live positions, fills, or PnL into Paper risk calculations. If PERPS is enabled but not in Paper mode, the Paper admission guard fails closed.
- Fail-closed admission: if a ledger snapshot cannot be read, the proposed allocation is invalid, a halt is set or its file is corrupt/unreadable, an enabled venue is not in Paper mode, any open Paper position lacks a fresh and valid mark, or current cross-venue Paper mark timestamps differ by more than 120 seconds, new entries are denied. The current skew check is applied at every admission, not only during UTC baseline capture. Existing PERPS paper positions remain included in the budget, mark-to-market loss and position count even when the PERPS engine is disabled. Missing/stale marks deny new entries without automatically writing an emergency halt.

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

- The guard has no configuration bypass and is hard-coded to Paper mode. The Command Center exposes the same snapshot and configured limits through a read-only status payload. Dashboard reads never create or rebase the UTC baseline; if the baseline is missing, the UI reports the preflight as blocked/unknown instead of displaying a fabricated zero. Non-Paper execution on either enabled arm is denied.
- The UTC baseline is normally captured within 300 seconds of midnight. If marks are missing, stale, or too far apart, capture remains pending until the 300-second window expires, then the baseline is permanently marked expired for that UTC date and new entries remain blocked. If the process starts after the window but there are no open positions and no fills since midnight in either ledger, a zero baseline is safe and may be captured late. Otherwise the bot will not rebase an active intraday account mid-day. A UTC clock rollback behind a previously stored date also blocks new entries.
- Capital utilization is an allocation limit, not a measure of maximum loss.
- Existing open positions are not liquidated by this guard. It denies new entries and persists a global halt after the combined realized daily-loss threshold is crossed.
- The CI gate targets Linux. Windows startup is not currently supported by the existing ARENA-owned runtime module, which imports POSIX `fcntl` unconditionally; this PR does not modify that claimed file.
- The guard is Paper-only. Live trading remains blocked until exchange execution, settlement, recovery, fee accounting, and failure-injection testing are separately validated.
