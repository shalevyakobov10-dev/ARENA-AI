# Autonomous AI Collaboration Charter

## Mission

Build and continuously improve PMMB as a reliable, evidence-led trading research and execution system. The user sets the high-level objective; the AI agents own day-to-day engineering discovery, prioritization, implementation, testing, and review. Do not require the user to assign individual engineering tasks.

## Shared working model

- GitHub is the sole shared source of truth for code, decisions, measurements, and handoffs.
- Arena Agent and ChatGPT are independent contributors, not a single shared process. They exchange work through branches, pull requests, review comments, `docs/journal/*.md`, `docs/DECISIONS.md`, and this repository's coordination rules.
- Each agent must read `docs/HANDOFF.md`, `docs/COORDINATION.md`, this charter, the latest journals, and recent commits before choosing work.
- Each agent independently identifies the highest-value next engineering task from verified defects, missing evidence, operational risks, test gaps, and the roadmap. Do not wait for the user to split the roadmap into tickets.
- Before editing, acquire a short-lived file claim under `docs/claims.json` and respect all existing claims and protected paths.
- Work on agent-specific branches. Never overwrite another agent's branch or push directly to `main` while the other agent may be active.
- Communicate through small, reviewable pull requests. Every PR must explain the problem, evidence, files changed, tests run, test results, risks, and next recommended step.
- Review the other agent's PRs when available: inspect the diff, reproduce relevant tests, identify correctness/security/regression issues, and leave actionable review feedback. Do not rubber-stamp.
- Append findings to the agent's journal. Add durable architectural decisions to `docs/DECISIONS.md`; update `docs/HANDOFF.md` only for material changes.

## Autonomous development loop

1. Reconcile the latest `main`, open PRs, file claims, journals, CI, and test baseline.
2. Select one bounded, high-impact task without asking the user to choose it.
3. State the hypothesis and measurable acceptance criteria before coding.
4. Implement the smallest safe change with focused tests.
5. Run the full offline test suite and applicable static/UI checks. Run network tests separately and report environment failures distinctly.
6. Measure before/after performance on identical data. Prefer walk-forward out-of-sample, calibration, fees, slippage, drawdown, and robustness over in-sample PnL.
7. Reject improvements that do not survive out-of-sample validation or that violate risk invariants.
8. Push a branch, open a PR, and record exact commit SHA, CI run, logs, and remaining blockers.
9. Review the other agent's changes and incorporate valid feedback in a new commit.
10. Repeat the loop on the next highest-value task when the agent is actively running.

## Evidence and honesty

- Distinguish verified live observations, offline tests, backtests, simulations, assumptions, and hypotheses.
- Never claim that a process is running 24/7, learning continuously, or reading live markets unless that runtime is actually deployed, observable, and monitored.
- Never infer readiness for real-money trading from a green unit-test suite or a profitable backtest alone.
- Performance claims must include sample size, period, costs, slippage assumptions, validation split, and drawdown. Preserve failed experiments and negative findings.
- Resolve conflicting documentation by tracing claims to source code, test outputs, logs, and reproducible data; do not silently copy claims from another document.

## Safety and release gates

- Keep paper/research mode as the default. No agent may enable live execution, submit/cancel real orders, or introduce live credentials as part of autonomous development.
- Do not commit `.env`, API keys, private keys, wallet seeds, account secrets, databases, runtime state, or logs.
- Never increase leverage, exposure, risk limits, or disable kill switches merely to improve reported returns.
- Any future live-trading proposal requires a separate explicit user authorization after independent readiness review, verified risk controls, realistic paper soak, and reproducible out-of-sample evidence.
- For external APIs, verify current official contracts, rate limits, product availability, and jurisdictional/access constraints before implementing order execution.
- Perpetuals integrations must be treated as a separate, high-risk execution venue; do not assume that a connector, API, or market type is available without verification.

## User involvement

The user should only be interrupted for decisions that genuinely require their authority (for example, account authorization, paid services, secret provisioning, or live-trading approval), not for routine engineering prioritization. Provide concise milestone reports with concrete artifacts and blockers. Do not promise background work between active sessions.
