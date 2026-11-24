# Portfolio Risk CLI

Use the portfolio-risk command to inspect the same unified ledger and mark-to-market snapshot used by the entry-admission gate.

Examples:

    pmmb portfolio-risk
    pmmb portfolio-risk --json

The command reports combined committed capital, the configured allocation ceiling, UTC day-start baseline state, mark freshness, daily mark-to-market PnL, remaining daily loss allowance, global halt state, and explicit entry blockers.

Exit status follows the project's status convention: 0 means the current entry gates are verified clear; 3 means blocked, stale, or not fully verified. This command is read-only: it does not create a baseline, clear a halt, change configuration, or submit orders.
