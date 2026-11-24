"""Deterministic paper soak and supervisor SIGKILL recovery tests.

The engine test injects synthetic Gamma/CLOB adapters. The supervisor test
runs the real paper_forever.sh with a tiny fake pmmb executable.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pmmb.data.clob import Book, Candle
from pmmb.data.store import Store
from pmmb.engine import Engine
from pmmb.runtime import check_health, read_heartbeat


class _SyntheticClob:
    def __init__(self) -> None:
        self._candles = [
            Candle(ts=1_700_000_000 + i * 300, price=0.50)
            for i in range(180)
        ]

    def get_book(self, token_id: str) -> Book:
        return Book(
            token_id=token_id,
            best_bid=0.495,
            best_ask=0.505,
            bid_size=2_000.0,
            ask_size=2_000.0,
            bids=[(0.495, 2_000.0)],
            asks=[(0.505, 2_000.0)],
        )

    def get_history(self, token_id: str, fidelity_min: int = 5,
                    lookback_candles: int = 144, **kwargs) -> list[Candle]:
        return self._candles[-lookback_candles:]

    def estimate_fill(self, book: Book, side: str, notional_usdc: float,
                      max_impact_pct: float = 0.02, allow_partial: bool = False):
        price = book.best_ask if side == "BUY" else book.best_bid
        return price, notional_usdc / price


def _cpu_pressure(cycle: int, worker: int) -> bytes:
    """Bounded deterministic CPU work; no network, subprocess or secret access."""
    material = f"pmmb-soak:{cycle}:{worker}".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", material, b"pmmb-soak-harness", 1_200)


def test_many_paper_cycles_keep_heartbeat_and_sqlite_healthy(cfg, market, tmp_path):
    cycles = int(os.getenv("PMMB_SOAK_CYCLES", "20"))
    workers = int(os.getenv("PMMB_SOAK_LOAD_WORKERS", "2"))
    assert 1 <= cycles <= 20_000
    assert 1 <= workers <= 8

    cfg.execution.mode = "paper"
    cfg.news.enabled = False
    state_dir = tmp_path / "state"
    store = Store(tmp_path / "soak.sqlite3")
    engine = Engine(
        cfg,
        store=store,
        clob=_SyntheticClob(),
        gamma=object(),
        state_dir=str(state_dir),
    )
    # Keep the engine's real cycle/heartbeat/DB path, but remove Gamma network I/O.
    engine.universe.scan = lambda: [market]

    last_ts = 0.0
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for expected_cycle in range(1, cycles + 1):
                futures = [
                    pool.submit(_cpu_pressure, expected_cycle, worker)
                    for worker in range(workers)
                ]
                assert all(future.result() for future in futures)

                stats = engine.run_once()
                assert stats.errors == 0

                heartbeat = read_heartbeat(state_dir)
                assert heartbeat is not None, "heartbeat disappeared during soak"
                assert heartbeat.cycle == expected_cycle
                assert heartbeat.pid == os.getpid()
                assert heartbeat.ts >= last_ts
                assert heartbeat.age_sec < 10
                assert check_health(max_age_sec=10, state_dir=state_dir).healthy
                last_ts = heartbeat.ts

        integrity = engine.store._conn.execute("PRAGMA integrity_check").fetchone()[0]
        assert integrity == "ok"
        assert not list(state_dir.glob("*.tmp")), "atomic heartbeat temp file was left behind"
    finally:
        engine.close()


def _wait_until(predicate, *, timeout: float = 8.0, description: str):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except (FileNotFoundError, json.JSONDecodeError, ProcessLookupError):
            pass
        time.sleep(0.02)
    raise AssertionError(f"timed out waiting for {description}")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def test_paper_supervisor_restarts_sigkill_child_and_stops_cleanly(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    source_script = repo_root / "scripts" / "paper_forever.sh"
    assert source_script.is_file()

    sandbox = tmp_path / "supervisor-sandbox"
    scripts_dir = sandbox / "scripts"
    fake_bin = sandbox / "bin"
    state_dir = sandbox / "state"
    scripts_dir.mkdir(parents=True)
    fake_bin.mkdir()
    state_dir.mkdir()
    supervisor_script = scripts_dir / "paper_forever.sh"
    shutil.copy2(source_script, supervisor_script)

    runs_path = state_dir / "starts.jsonl"
    heartbeat_path = state_dir / "heartbeat.json"
    fake_pmmb = fake_bin / "pmmb"
    fake_pmmb.write_text(
        """#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

state = Path(os.environ["PMMB_SOAK_STATE_DIR"])
state.mkdir(parents=True, exist_ok=True)
runs = state / "starts.jsonl"
hb = state / "heartbeat.json"
run_id = len(runs.read_text(encoding="utf-8").splitlines()) + 1 if runs.exists() else 1
with runs.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"run": run_id, "pid": os.getpid()}) + "\\n")
    stream.flush()

cycle = 0
while True:
    cycle += 1
    tmp = hb.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "ts": time.time(), "cycle": cycle, "pid": os.getpid(), "mode": "paper"
    }), encoding="utf-8")
    os.replace(tmp, hb)
    time.sleep(0.02)
""",
        encoding="utf-8",
    )
    fake_pmmb.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = str(fake_bin) + os.pathsep + env.get("PATH", "")
    env["PMMB_SOAK_STATE_DIR"] = str(state_dir)
    env["PMMB_RESTART_DELAY_SEC"] = "0.05"

    supervisor = subprocess.Popen(
        ["bash", str(supervisor_script), "1"],
        cwd=sandbox,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    child_pids: list[int] = []
    try:
        first = _wait_until(
            lambda: (_read_jsonl(runs_path) or [None])[0],
            description="first paper child",
        )
        first_pid = int(first["pid"])
        child_pids.append(first_pid)
        _wait_until(
            lambda: (
                (lambda hb: hb if hb and hb.get("pid") == first_pid and hb.get("cycle", 0) >= 3 else None)(
                    json.loads(heartbeat_path.read_text(encoding="utf-8"))
                )
            ),
            description="first child heartbeat",
        )

        # Simulate an uncatchable crash of the bot process managed by the shell loop.
        os.kill(first_pid, signal.SIGKILL)

        second = _wait_until(
            lambda: (
                (lambda rows: rows[1] if len(rows) >= 2 else None)(_read_jsonl(runs_path))
            ),
            description="supervisor restart after SIGKILL",
        )
        second_pid = int(second["pid"])
        child_pids.append(second_pid)
        assert second_pid != first_pid
        recovered = _wait_until(
            lambda: (
                (lambda hb: hb if hb and hb.get("pid") == second_pid and hb.get("cycle", 0) >= 3 else None)(
                    json.loads(heartbeat_path.read_text(encoding="utf-8"))
                )
            ),
            description="recovered child heartbeat",
        )
        assert recovered["mode"] == "paper"
    finally:
        if supervisor.poll() is None:
            supervisor.terminate()
            try:
                supervisor.wait(timeout=4)
            except subprocess.TimeoutExpired:
                supervisor.kill()
                supervisor.wait(timeout=2)
        # Defensive cleanup keeps a failed test from leaking a fake worker.
        for pid in child_pids:
            if _pid_exists(pid):
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    assert supervisor.returncode == 0
    assert len(_read_jsonl(runs_path)) >= 2
    assert all(not _pid_exists(pid) for pid in child_pids), "supervisor left a child process running"
