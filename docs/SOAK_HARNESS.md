# Soak harness

The harness validates paper-mode runtime resilience without contacting Gamma, CLOB,
an exchange, or any order-submission endpoint.

## What it exercises

1. Repeated `Engine.run_once()` cycles with synthetic market data and bounded
   concurrent CPU work. Every cycle must publish a fresh, parseable heartbeat
   with the expected cycle number and PID.
2. SQLite integrity after the run, and the absence of leftover atomic-write
   temporary files.
3. The real `scripts/paper_forever.sh` supervisor in a temporary sandbox. A fake
   `pmmb` child writes a heartbeat; the test kills that child with `SIGKILL`,
   verifies that the supervisor starts a new child and observes its heartbeat,
   then sends `SIGTERM` to the supervisor and verifies that it stops the
   managed child.

The supervisor test does not run the live CLI or use the user's database.

## Run locally

Install development dependencies once:

```bash
pip install -e ".[dev]"
```

Run a 500-cycle soak with two load workers:

```bash
PMMB_SOAK_LOAD_WORKERS=2 ./scripts/run_soak_harness.sh 500
```

Use `PMMB_SOAK_LOAD_WORKERS` from 1 to 8 and a cycle count from 1 to 20,000.
The default command runs 250 cycles; CI runs the test module with its short
20-cycle default.

## Supervisor restart delay

`scripts/paper_forever.sh` keeps its production default of 30 seconds between
restarts. `PMMB_RESTART_DELAY_SEC` allows a non-negative numeric override for
controlled deployments and fast automated recovery drills. INT/TERM now stop
the managed child and wait for it before the supervisor exits.
