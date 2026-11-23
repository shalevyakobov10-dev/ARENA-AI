"""
שכבת הריצה העצמאית: דופק (heartbeat), מצב קריא, ובדיקת בריאות.

הבוט אמור לרוץ לבד על המחשב ימים שלמים. שלושה דברים מאפשרים את זה:
  1. **דופק** — קובץ שמתעדכן כל מחזור. אם הוא מתיישן, משהו תקוע.
  2. **מצב קריא** — status מוכן ל-JSON, כדי לראות מהטלפון מה קורה.
  3. **גלאי תקיעות** — פונקציה שמכריזה "לא בריא" ומאפשרת ל-watchdog להרים.
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_NAME = "heartbeat.json"
HALT_NAME = "halt.json"


class ProcessLockError(RuntimeError):
    """מופיע כשמנסים להריץ מופע כפול של הבוט על אותו מצב."""


class ProcessLock:
    """מניעת ריצה כפולה (singleton lock) באמצעות flock אטומי."""

    def __init__(self, name: str, state_dir: str | Path | None = None) -> None:
        base = Path(state_dir) if state_dir is not None else default_state_dir()
        self.path = base / f"{name}.lock"
        self._fh = None

    def acquire(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            fh.seek(0)
            owner = fh.read().strip() or "?"
            fh.close()
            raise ProcessLockError(
                f"כבר רץ מופע פעיל ({self.path}, pid={owner}) — עצור אותו לפני הפעלה נוספת"
            ) from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh
        return self

    def release(self) -> None:
        if self._fh is not None:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            try:
                self._fh.close()
            finally:
                self._fh = None

    def __enter__(self) -> "ProcessLock":
        return self.acquire()

    def __exit__(self, *args) -> None:
        self.release()


def default_state_dir() -> Path:
    """נקרא בזמן ריצה (לא בזמן import) כדי שכיבוד משתני סביבה יהיה אמיתי."""
    return Path(os.environ.get("PMMB_STATE_DIR", "state"))


def heartbeat_path(state_dir: str | Path | None = None) -> Path:
    base = Path(state_dir) if state_dir is not None else default_state_dir()
    return base / HEARTBEAT_NAME


def halt_path(state_dir: str | Path | None = None) -> Path:
    base = Path(state_dir) if state_dir is not None else default_state_dir()
    return base / HALT_NAME


@dataclass
class HaltFlag:
    reason: str
    source: str = "manual"      # manual / phone / risk
    ts: float = 0.0

    @property
    def iso(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()

    def as_dict(self) -> dict:
        return {"ts": round(self.ts, 3), "iso": self.iso,
                "source": self.source, "reason": self.reason}


def write_halt(reason: str, *, source: str = "manual",
               state_dir: str | Path | None = None) -> Path:
    flag = HaltFlag(reason=reason or "עצירה ידנית", source=source, ts=time.time())
    p = halt_path(state_dir)
    _atomic_write(p, flag.as_dict())
    return p


def read_halt(state_dir: str | Path | None = None) -> HaltFlag | None:
    p = halt_path(state_dir)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return HaltFlag(
        reason=str(d.get("reason") or "עצירה ידנית"),
        source=str(d.get("source") or "manual"),
        ts=float(d.get("ts") or 0.0),
    )


def clear_halt(state_dir: str | Path | None = None) -> bool:
    p = halt_path(state_dir)
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False


def _atomic_write(path: Path, payload: dict) -> None:
    """כתיבה אטומית — אף פעם לא משאירים קובץ חצי-כתוב לקורא."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class Heartbeat:
    ts: float
    cycle: int = 0
    mode: str = "paper"
    engine: str = "meanrev"
    equity: float = 0.0
    cash: float = 0.0
    exposure: float = 0.0
    positions: int = 0
    scanned: int = 0
    signalled: int = 0
    entries: int = 0
    exits: int = 0
    errors: int = 0
    halted: bool = False
    halt_reason: str = ""
    pid: int = 0
    skipped: dict = field(default_factory=dict)   # למה לא נסחר: סיבת דחייה → מונה
    guards: dict = field(default_factory=dict)    # מצב ההגנות (סטופ יומי, drawdown...)
    extra: dict = field(default_factory=dict)

    @property
    def age_sec(self) -> float:
        return max(0.0, time.time() - self.ts)

    @property
    def iso(self) -> str:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc).isoformat()

    def as_dict(self) -> dict:
        d = {
            "ts": round(self.ts, 3), "iso": self.iso, "cycle": self.cycle,
            "mode": self.mode, "engine": self.engine,
            "equity": round(self.equity, 2), "cash": round(self.cash, 2),
            "exposure": round(self.exposure, 2), "positions": self.positions,
            "last_cycle": {"scanned": self.scanned, "signalled": self.signalled,
                           "entries": self.entries, "exits": self.exits,
                           "errors": self.errors},
            "halted": self.halted, "halt_reason": self.halt_reason, "pid": self.pid,
            "skipped": dict(self.skipped), "guards": dict(self.guards),
        }
        if self.extra:
            d.update(self.extra)
        return d


def write_heartbeat(hb: Heartbeat, state_dir: str | Path | None = None) -> Path:
    p = heartbeat_path(state_dir)
    _atomic_write(p, hb.as_dict())
    return p


def read_heartbeat(state_dir: str | Path | None = None) -> Heartbeat | None:
    p = heartbeat_path(state_dir)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    lc = d.get("last_cycle", {})
    known = {"ts", "iso", "cycle", "mode", "engine", "equity", "cash", "exposure",
             "positions", "last_cycle", "halted", "halt_reason", "pid", "skipped", "guards"}
    return Heartbeat(
        ts=float(d.get("ts", 0)),
        cycle=int(d.get("cycle", 0)),
        mode=d.get("mode", "paper"),
        engine=d.get("engine", "meanrev"),
        equity=float(d.get("equity", 0)),
        cash=float(d.get("cash", 0)),
        exposure=float(d.get("exposure", 0)),
        positions=int(d.get("positions", 0)),
        scanned=int(lc.get("scanned", 0)),
        signalled=int(lc.get("signalled", 0)),
        entries=int(lc.get("entries", 0)),
        exits=int(lc.get("exits", 0)),
        errors=int(lc.get("errors", 0)),
        halted=bool(d.get("halted", False)),
        halt_reason=d.get("halt_reason", ""),
        pid=int(d.get("pid", 0)),
        skipped=dict(d.get("skipped") or {}),
        guards=dict(d.get("guards") or {}),
        extra={k: v for k, v in d.items() if k not in known},
    )


@dataclass
class Health:
    healthy: bool
    reason: str
    heartbeat: Heartbeat | None

    def as_dict(self) -> dict:
        return {
            "healthy": self.healthy, "reason": self.reason,
            "age_sec": round(self.heartbeat.age_sec, 1) if self.heartbeat else None,
            "halted": self.heartbeat.halted if self.heartbeat else None,
            "heartbeat": self.heartbeat.as_dict() if self.heartbeat else None,
        }


def check_health(*, max_age_sec: float = 300, state_dir: str | Path | None = None) -> Health:
    """
    בריא = יש דופק, הוא טרי, ואין עצירה (פנימית או מהטלפון/CLI).
    max_age_sec צריך להיות לפחות פי 2–3 מרווח המחזור.
    """
    hb = read_heartbeat(state_dir)
    halt = read_halt(state_dir)
    if halt is not None:
        return Health(False, f"הבוט עצור ({halt.source}): {halt.reason}", hb)
    if hb is None:
        return Health(False, "אין קובץ דופק — הבוט לא רץ מעולם או שהנתיב שגוי", None)
    if hb.halted:
        return Health(False, f"הבוט עצר את עצמו: {hb.halt_reason or 'ללא סיבה'}", hb)
    if hb.age_sec > max_age_sec:
        return Health(False, f"הדופק מתיישן ({hb.age_sec / 60:.1f} דקות) — ייתכן שהבוט תקוע", hb)
    return Health(True, "תקין", hb)
