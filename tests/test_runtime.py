"""דופק ובריאות — הבסיס לכך שהבוט יכול לרוץ לבד."""
import json
import time

from pmmb.runtime import (Heartbeat, check_health, heartbeat_path, read_heartbeat,
                          write_heartbeat)


def _hb(**kw) -> Heartbeat:
    base = dict(ts=time.time(), cycle=7, mode="paper", engine="meanrev",
                equity=1010.5, cash=900.0, exposure=110.5, positions=2,
                scanned=50, signalled=3, entries=1, exits=1, errors=0, pid=4242)
    base.update(kw)
    return Heartbeat(**base)


def test_roundtrip(tmp_path):
    write_heartbeat(_hb(), tmp_path)
    hb = read_heartbeat(tmp_path)
    assert hb is not None
    assert hb.cycle == 7 and hb.equity == 1010.5 and hb.positions == 2
    assert hb.entries == 1 and hb.pid == 4242
    assert hb.age_sec < 5


def test_write_is_atomic_no_tmp_left(tmp_path):
    write_heartbeat(_hb(), tmp_path)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert "heartbeat.json" in files
    assert not any(f.endswith(".tmp") for f in files)


def test_dict_is_json_serializable(tmp_path):
    write_heartbeat(_hb(), tmp_path)
    raw = json.loads(heartbeat_path(tmp_path).read_text(encoding="utf-8"))
    assert raw["last_cycle"]["scanned"] == 50
    assert "iso" in raw and raw["mode"] == "paper"


def test_missing_heartbeat_is_unhealthy(tmp_path):
    h = check_health(state_dir=tmp_path)
    assert not h.healthy
    assert "אין קובץ דופק" in h.reason


def test_fresh_heartbeat_is_healthy(tmp_path):
    write_heartbeat(_hb(), tmp_path)
    assert check_health(state_dir=tmp_path).healthy


def test_stale_heartbeat_is_unhealthy(tmp_path):
    write_heartbeat(_hb(ts=time.time() - 3600), tmp_path)
    h = check_health(max_age_sec=300, state_dir=tmp_path)
    assert not h.healthy and "מתיישן" in h.reason


def test_halted_bot_is_unhealthy_even_if_fresh(tmp_path):
    write_heartbeat(_hb(halted=True, halt_reason="drawdown 21.0%"), tmp_path)
    h = check_health(state_dir=tmp_path)
    assert not h.healthy
    assert "עצר את עצמו" in h.reason and "drawdown" in h.reason


def test_explicit_state_dir_overrides_default(monkeypatch, tmp_path):
    monkeypatch.setenv("PMMB_STATE_DIR", str(tmp_path / "custom"))
    write_heartbeat(_hb())
    assert (tmp_path / "custom" / "heartbeat.json").exists()
