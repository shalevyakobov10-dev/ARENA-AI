# PMMB Command Center — Operations View

The browser command center is served by the existing PMMB server. Open the local dashboard at `http://127.0.0.1:8787/` after starting `pmmb serve`.

## Operations tab

The home screen also includes a Portfolio Risk Desk with combined gross-notional exposure, Polymarket exposure against its configured arm cap, PERPS margin against its configured margin cap, and average PERPS leverage. It recalculates from each refreshed state payload. It is a monitoring surface, not an order-admission controller.

The **מרכז תפעול וניטור** tab adds a consolidated read-only view of:

- process heartbeat, emergency halt state, and trader-loop status;
- last recorded market-stream, news, learning, reconciliation, and backup timestamps;
- cumulative database telemetry (ticks, books, signals, news, and market-intelligence rows);
- combined account equity and open positions across Polymarket and PERPS;
- gross exposure indicators, PERPS margin usage, and nearest liquidation distance;
- readiness gates and recent persisted system events.

The header reports backend connectivity and the timestamp of the last successful state refresh; failed refreshes are surfaced instead of silently leaving stale data on screen. Returning to the browser tab triggers an immediate refresh. The Risk Desk shows per-arm limits and combined gross-notional telemetry, but never treats gross notional as maximum loss. When the read-only status payload includes `unified_risk`, the desk additionally displays the enforced Paper shared budget, committed amount, utilization, combined marked PnL, daily-loss threshold, position count, mark freshness/failures and persistent halt reason. When that backend snapshot is absent, those fields remain explicitly unavailable rather than inferred or hardcoded. The shared entry gate is implemented separately in the engine changes tracked by PR #9, with mark-to-market protection in dependent PR #10; the status API integration is tracked in issue #11.

## Safe use

- Keep `execution.mode` and `perps.mode` set to `paper` during development.
- The Polymarket scan button is enabled only when `execution.mode=paper`; the PERPS scan button is independently gated by `perps.enabled=true` and `perps.mode=paper`. Missing PERPS mode data fails closed (disabled).
- The reconciliation, news refresh, and backup buttons call existing server endpoints; they do not submit market orders.
- Remote access should remain behind the server authentication controls. Do not expose an unauthenticated dashboard to the public internet.
- This view is operational software, not a guarantee of profitability or live-trading readiness.
