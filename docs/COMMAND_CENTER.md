# PMMB Command Center — Operations View

The browser command center is served by the existing PMMB server. Open the local dashboard at `http://127.0.0.1:8787/` after starting `pmmb serve`.

## Operations tab

The **מרכז תפעול וניטור** tab adds a consolidated read-only view of:

- process heartbeat, emergency halt state, and trader-loop status;
- last recorded market-stream, news, learning, reconciliation, and backup timestamps;
- cumulative database telemetry (ticks, books, signals, news, and market-intelligence rows);
- combined account equity and open positions across Polymarket and PERPS;
- gross exposure indicators, PERPS margin usage, and nearest liquidation distance;
- readiness gates and recent persisted system events.

The combined exposure figures are monitoring indicators, not an enforced cross-venue risk budget. The current engines retain their own risk rules. A shared portfolio risk gate is a separate engineering task and must be implemented and tested in the execution path before the dashboard may describe it as enforced.

## Safe use

- Keep `execution.mode` and `perps.mode` set to `paper` during development.
- The manual scan buttons on the operations tab are disabled outside Paper mode.
- The reconciliation, news refresh, and backup buttons call existing server endpoints; they do not submit market orders.
- Remote access should remain behind the server authentication controls. Do not expose an unauthenticated dashboard to the public internet.
- This view is operational software, not a guarantee of profitability or live-trading readiness.
