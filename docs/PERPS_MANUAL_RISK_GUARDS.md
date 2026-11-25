# Manual PERPS Quick Trade — risk parity

The Command Center's manual PERPS order endpoint is Paper-only, requires the PERPS arm to be enabled, and must not be a weaker route than signal-driven entries.

Before the broker is called, manual entry now checks:

- The process-wide uncertain-execution latch, enabled-arm state, and the PERPS daily-loss / drawdown kill switch.
- PERPS maximum open positions and maximum positions in the requested direction.
- Maximum isolated margin per position and remaining total portfolio margin.
- Available cash and the shared cross-venue Paper allocation gate.
- Correct-side Stop-Loss / Take-Profit levels and a safe leverage cap derived from the configured `liquidation_buffer_mult`.

If the stop distance requires less than the minimum supported 2x leverage, the manual order is rejected before the broker is called. Manual order sizing is not silently increased or allowed to exceed the per-arm limits. Existing positions remain closeable through the normal reduce-only close path.

This is still Paper execution only. The tests use local stub exchanges and paper brokers; they do not submit exchange orders or validate production fills.
