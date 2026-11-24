# Walk-forward parameter promotion guard

## Problem

The walk-forward evaluator aggregates out-of-sample (OOS) results from each
fold using that fold's independently selected best parameters. The learner then
selects the final fold's parameter set for the single configuration written to
the running bot. If folds select different parameter sets, aggregate OOS PnL
does not measure the one configuration being promoted.

## Guard

A candidate is eligible for automatic paper promotion only when every OOS fold
selected exactly the same parameter dictionary. The existing OOS trade-count,
consistency, positive PnL excluding the top result, and improvement gates still
apply. If fold parameters disagree, promotion is blocked and the report records
`parameters_stable: false`.

This is deliberately conservative. It may defer useful adaptations, but it
prevents a walk-forward ensemble result from being misrepresented as evidence
for a single live configuration.

## Scope

- Applies to self-learning configuration promotion.
- Does not change signal generation, execution, or any exchange connection.
- Does not enable live auto-application.
- Validation is synthetic/unit-test based; it is not evidence of strategy
  profitability or a substitute for a longer OOS evaluation.
