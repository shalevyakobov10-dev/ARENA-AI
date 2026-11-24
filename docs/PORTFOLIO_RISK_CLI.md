# Portfolio Risk CLI

Use the read-only portfolio-risk command to inspect the same unified ledger and mark-to-market snapshot used by the entry-admission gate.

Examples:

    pmmb portfolio-risk
    pmmb portfolio-risk --json

The command reports combined committed capital, the configured allocation ceiling, UTC day-start baseline state, mark freshness, daily mark-to-market PnL, remaining daily loss allowance, global halt state, and explicit shared-gate blockers.

Exit status follows the project convention: 0 means the shared portfolio admission gates are verified clear; 3 means blocked, stale, or not fully verified. A clear shared gate does not approve a market signal or bypass per-market risk checks.

This command is read-only: it does not create a baseline, clear a halt, change configuration, or submit orders. If the ledger cannot be opened or verified, it returns exit code 3.
