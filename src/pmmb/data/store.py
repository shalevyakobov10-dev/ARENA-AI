"""שכבת התמדה — SQLite. טבלאות: ticks, signals, fills, positions, equity, events."""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ticks (
    token_id TEXT NOT NULL,
    ts       INTEGER NOT NULL,
    price    REAL NOT NULL,
    PRIMARY KEY (token_id, ts)
);

CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    condition_id  TEXT,
    token_id      TEXT,
    direction     TEXT,
    score         REAL,
    fair_price    REAL,
    market_price  REAL,
    edge          REAL,
    reason        TEXT,
    features      TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(ts);

CREATE TABLE IF NOT EXISTS fills (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    mode          TEXT NOT NULL,          -- paper / live
    token_id      TEXT NOT NULL,
    condition_id  TEXT,
    side          TEXT NOT NULL,
    price         REAL NOT NULL,
    size          REAL NOT NULL,
    fee           REAL DEFAULT 0,
    notional      REAL,
    reason        TEXT,
    order_id      TEXT,
    realized      REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts);

CREATE TABLE IF NOT EXISTS positions (
    token_id      TEXT PRIMARY KEY,
    condition_id  TEXT,
    mode          TEXT,
    direction     TEXT,
    size          REAL,
    avg_price     REAL,
    opened_at     INTEGER,
    entry_score   REAL,
    stop_price    REAL,
    target_price  REAL,
    question      TEXT,
    closed_at     INTEGER,
    exit_reason   TEXT,
    realized_pnl  REAL
);

CREATE TABLE IF NOT EXISTS equity (
    ts        INTEGER NOT NULL,
    equity    REAL NOT NULL,
    cash      REAL NOT NULL,
    exposure  REAL NOT NULL,
    positions INTEGER,
    PRIMARY KEY (ts)
);

CREATE TABLE IF NOT EXISTS books (
    token_id   TEXT NOT NULL,
    ts         INTEGER NOT NULL,
    mid        REAL,
    best_bid   REAL,
    best_ask   REAL,
    bid_depth  REAL,
    ask_depth  REAL,
    imbalance  REAL,
    PRIMARY KEY (token_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_books_ts ON books(ts);

CREATE TABLE IF NOT EXISTS events (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    ts    INTEGER NOT NULL,
    level TEXT,
    kind  TEXT,
    msg   TEXT,
    data  TEXT
);

CREATE TABLE IF NOT EXISTS news_items (
    id             TEXT PRIMARY KEY,
    ts             INTEGER NOT NULL,
    title          TEXT NOT NULL,
    source         TEXT DEFAULT '',
    url            TEXT DEFAULT '',
    query          TEXT DEFAULT '',
    category       TEXT DEFAULT 'macro',
    sentiment      REAL DEFAULT 0,
    impact         REAL DEFAULT 0,
    matched_tokens TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_news_ts ON news_items(ts);

CREATE TABLE IF NOT EXISTS signal_outcomes (
    signal_id    INTEGER PRIMARY KEY,
    token_id     TEXT NOT NULL,
    ts           INTEGER NOT NULL,
    direction    TEXT,
    entry_price  REAL,
    fair_price   REAL,
    edge         REAL,
    z_score      REAL,
    sector       TEXT DEFAULT '',
    news_impact  REAL DEFAULT 0,
    price_6h     REAL,
    price_24h    REAL,
    price_48h    REAL,
    realized_24h REAL,
    realized_48h REAL,
    evaluated_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_sig_outcomes_ts ON signal_outcomes(ts);

CREATE TABLE IF NOT EXISTS learning_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            INTEGER NOT NULL,
    mode          TEXT NOT NULL,
    baseline_oos  REAL,
    candidate_oos REAL,
    consistency   REAL,
    oos_trades    INTEGER,
    baseline_cfg  TEXT,
    candidate_cfg TEXT,
    applied       INTEGER DEFAULT 0,
    summary       TEXT,
    details       TEXT
);

CREATE TABLE IF NOT EXISTS market_intel (
    condition_id  TEXT PRIMARY KEY,
    token_id      TEXT NOT NULL,
    question      TEXT NOT NULL,
    sector        TEXT DEFAULT 'other',
    price         REAL,
    spread        REAL,
    bid_depth     REAL DEFAULT 0,
    ask_depth     REAL DEFAULT 0,
    imbalance     REAL DEFAULT 0,
    volume_24h    REAL DEFAULT 0,
    volume_ratio  REAL DEFAULT 1.0,
    chg_1h        REAL,
    chg_6h        REAL,
    chg_24h       REAL,
    z_score       REAL,
    edge_net      REAL,
    rsi           REAL,
    setup_tier    TEXT DEFAULT 'B',
    microprice    REAL,
    news_count    INTEGER DEFAULT 0,
    news_impact   REAL DEFAULT 0,
    hours_left    REAL,
    status        TEXT DEFAULT 'WATCH',
    reason        TEXT DEFAULT '',
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intel_upd ON market_intel(updated_at);

CREATE TABLE IF NOT EXISTS autopilot_runs (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      INTEGER NOT NULL,
    task    TEXT NOT NULL,
    status  TEXT NOT NULL,
    summary TEXT NOT NULL,
    details TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_ap_ts ON autopilot_runs(ts);
"""


class Store:
    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=10.0)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA busy_timeout=5000")
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        self._conn.executescript(SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """מיגרציות קלות — עמודות שנוספו אחרי שה-DB כבר נוצר."""
        cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(fills)")}
        if "realized" not in cols:
            self._conn.execute("ALTER TABLE fills ADD COLUMN realized REAL DEFAULT 0")
            self._conn.commit()
            log.info("migrated: fills.realized נוסף")
        eq_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(equity)")}
        if "mode" not in eq_cols:
            self._conn.execute("ALTER TABLE equity ADD COLUMN mode TEXT DEFAULT 'paper'")
            self._conn.commit()
            log.info("migrated: equity.mode נוסף")
        pos_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(positions)")}
        if "event_id" not in pos_cols:
            self._conn.execute("ALTER TABLE positions ADD COLUMN event_id TEXT DEFAULT ''")
            self._conn.commit()
            log.info("migrated: positions.event_id נוסף")
        out_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(signal_outcomes)")}
        if "realized_6h" not in out_cols:
            self._conn.execute("ALTER TABLE signal_outcomes ADD COLUMN realized_6h REAL")
            self._conn.commit()
            log.info("migrated: signal_outcomes.realized_6h נוסף")
        mi_cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(market_intel)")}
        for col, cdef in (("rsi", "REAL"), ("setup_tier", "TEXT DEFAULT 'B'"), ("microprice", "REAL")):
            if col not in mi_cols:
                self._conn.execute(f"ALTER TABLE market_intel ADD COLUMN {col} {cdef}")
                self._conn.commit()
                log.info("migrated: market_intel.%s נוסף", col)

    # ------------------------------------------------------------------
    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    #  ticks
    # ------------------------------------------------------------------
    def insert_ticks(self, rows: list[tuple[str, int, float]]) -> None:
        if not rows:
            return
        with self.tx() as c:
            c.executemany(
                "INSERT OR REPLACE INTO ticks(token_id, ts, price) VALUES (?,?,?)", rows
            )

    def record_book(self, token_id: str, ts: int, book, levels: int = 5) -> None:
        bid_depth, ask_depth = book.depth(levels)
        with self.tx() as c:
            c.execute(
                """INSERT OR REPLACE INTO books(ts, token_id, mid, best_bid, best_ask,
                       bid_depth, ask_depth, imbalance) VALUES (?,?,?,?,?,?,?,?)""",
                (ts, token_id, book.mid, book.best_bid, book.best_ask,
                 bid_depth, ask_depth, book.imbalance(levels)),
            )

    def get_books(self, token_id: str | None = None, limit: int = 100000):
        if token_id:
            return self._conn.execute(
                "SELECT * FROM books WHERE token_id=? ORDER BY ts LIMIT ?", (token_id, limit)
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM books ORDER BY token_id, ts LIMIT ?", (limit,)
        ).fetchall()

    def get_ticks(self, token_id: str, limit: int = 500) -> list[tuple[int, float]]:
        cur = self._conn.execute(
            "SELECT ts, price FROM ticks WHERE token_id=? ORDER BY ts DESC LIMIT ?",
            (token_id, limit),
        )
        return [(int(r["ts"]), float(r["price"])) for r in reversed(cur.fetchall())]

    # ------------------------------------------------------------------
    #  signals / fills / equity / events
    # ------------------------------------------------------------------
    def record_signal(self, s) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO signals(ts, condition_id, token_id, direction, score,
                       fair_price, market_price, edge, reason, features)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(s.created_at.timestamp()),
                    s.condition_id,
                    s.token_id,
                    s.direction,
                    s.score,
                    s.fair_price,
                    s.market_price,
                    s.edge,
                    s.reason,
                    json.dumps(s.features, ensure_ascii=False),
                ),
            )

    def record_fill(self, f, mode: str, realized: float = 0.0) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO fills(ts, mode, token_id, condition_id, side, price, size,
                       fee, notional, reason, order_id, realized)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(f.ts.timestamp()),
                    mode,
                    f.token_id,
                    f.condition_id,
                    f.side,
                    f.price,
                    f.size,
                    f.fee,
                    f.notional,
                    getattr(f, "reason", ""),
                    f.order_id,
                    realized,
                ),
            )
            if realized:
                c.execute(
                    "UPDATE positions SET realized_pnl = COALESCE(realized_pnl,0) + ? WHERE token_id=?",
                    (realized, f.token_id),
                )

    def upsert_position(self, p, mode: str) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO positions(token_id, condition_id, mode, direction, size, avg_price,
                       opened_at, entry_score, stop_price, target_price, question, event_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(token_id) DO UPDATE SET
                       size=excluded.size, avg_price=excluded.avg_price,
                       stop_price=excluded.stop_price, target_price=excluded.target_price,
                       direction=excluded.direction, question=excluded.question,
                       event_id=CASE WHEN excluded.event_id != ''
                                     THEN excluded.event_id ELSE positions.event_id END,
                       closed_at=NULL, exit_reason=NULL,
                       -- פוזיציה שעדיין פתוחה שומרת על הרווח הממוצע המצטבר;
                       -- פוזיציה שנסגרה ומתחדשת מתחילה מ-0
                       realized_pnl=CASE WHEN positions.closed_at IS NOT NULL
                                         THEN 0 ELSE positions.realized_pnl END""",
                (
                    p.token_id,
                    p.condition_id,
                    mode,
                    p.direction,
                    p.size,
                    p.avg_price,
                    int(p.opened_at.timestamp()),
                    p.entry_score,
                    p.stop_price,
                    p.target_price,
                    p.question,
                    getattr(p, "event_id", "") or "",
                ),
            )

    def close_position(self, token_id: str, reason: str, realized_pnl: float) -> None:
        with self.tx() as c:
            cur = c.execute(
                "UPDATE positions SET size=0, closed_at=?, exit_reason=? WHERE token_id=?",
                (int(datetime.now(tz=timezone.utc).timestamp()), reason, token_id),
            )
            if cur.rowcount == 0:
                # אין רשומה לסגור — קורה אם הפוזיציה נפתחה לפני שה-Store נרשם.
                # לא זורקים: רושמים אירוע כדי שיהיה עקבה.
                log.warning("close_position: אין רשומת פוזיציה עבור %s", token_id[:12])
                c.execute(
                    "INSERT INTO events(ts, level, kind, msg, data) VALUES (?,?,?,?,?)",
                    (int(datetime.now(tz=timezone.utc).timestamp()), "WARNING",
                     "close_missing", f"סגירה ללא פוזיציה: {token_id[:16]}",
                     f'{{"reason": "{reason}", "pnl": {realized_pnl}}}'),
                )

    def snapshot_equity(self, snap, mode: str = "paper") -> None:
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO equity(ts, equity, cash, exposure, positions, mode) "
                "VALUES (?,?,?,?,?,?)",
                (int(snap.ts.timestamp()), snap.equity, snap.cash, snap.exposure,
                 snap.open_positions, mode),
            )

    def event(self, kind: str, msg: str, level: str = "INFO", data: dict[str, Any] | None = None) -> None:
        with self.tx() as c:
            c.execute(
                "INSERT INTO events(ts, level, kind, msg, data) VALUES (?,?,?,?,?)",
                (
                    int(datetime.now(tz=timezone.utc).timestamp()),
                    level,
                    kind,
                    msg,
                    json.dumps(data or {}, ensure_ascii=False, default=str),
                ),
            )

    # ------------------------------------------------------------------
    #  אנליטיקה
    # ------------------------------------------------------------------
    def realized_pnl_since(self, ts: int) -> float:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(realized_pnl),0) AS s FROM positions WHERE closed_at >= ?", (ts,)
        ).fetchone()
        return float(row["s"] or 0.0)

    def peak_equity(self, mode: str | None = None) -> float:
        if mode:
            row = self._conn.execute(
                "SELECT COALESCE(MAX(equity),0) AS s FROM equity WHERE mode=? OR mode IS NULL",
                (mode,),
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COALESCE(MAX(equity),0) AS s FROM equity").fetchone()
        return float(row["s"] or 0.0)

    def latest_marks(self, token_ids: list[str]) -> dict[str, float]:
        """המחיר האחרון הידוע לכל טוקן (books עדיף על ticks)."""
        marks: dict[str, float] = {}
        for tid in token_ids:
            row = self._conn.execute(
                "SELECT mid, best_bid FROM books WHERE token_id=? ORDER BY ts DESC LIMIT 1",
                (tid,),
            ).fetchone()
            if row and (row["best_bid"] or row["mid"]):
                marks[tid] = float(row["best_bid"] or row["mid"])
                continue
            trow = self._conn.execute(
                "SELECT price FROM ticks WHERE token_id=? ORDER BY ts DESC LIMIT 1",
                (tid,),
            ).fetchone()
            if trow:
                marks[tid] = float(trow["price"])
        return marks

    def load_portfolio_state(self, mode: str, starting_cash: float,
                             now: datetime | None = None) -> dict[str, Any]:
        """משחזר מצב תיק מדויק אחרי הפעלה מחדש: פוזיציות, מזומן, רווח יומי ושיא."""
        from ..models import Position

        now = now or datetime.now(tz=timezone.utc)
        day_start = int(now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

        pos_rows = self.open_positions(mode)
        positions: list[Position] = []
        for r in pos_rows:
            opened_ts = int(r["opened_at"] or int(now.timestamp()))
            positions.append(Position(
                token_id=str(r["token_id"]),
                condition_id=str(r["condition_id"] or ""),
                direction=r["direction"] or "LONG",
                size=float(r["size"] or 0.0),
                avg_price=float(r["avg_price"] or 0.0),
                opened_at=datetime.fromtimestamp(opened_ts, tz=timezone.utc),
                entry_score=float(r["entry_score"] or 0.0),
                stop_price=float(r["stop_price"]) if r["stop_price"] is not None else None,
                target_price=float(r["target_price"]) if r["target_price"] is not None else None,
                question=str(r["question"] or ""),
                event_id=str(r["event_id"] or "") if "event_id" in r.keys() else "",
            ))

        fill_rows = list(self._conn.execute(
            "SELECT side, price, size, fee, realized, ts FROM fills WHERE mode=? ORDER BY ts, id",
            (mode,),
        ).fetchall())
        if fill_rows:
            cash = starting_cash
            realized_total = 0.0
            realized_today = 0.0
            for fr in fill_rows:
                px = float(fr["price"])
                sz = float(fr["size"])
                fee = float(fr["fee"] or 0.0)
                rz = float(fr["realized"] or 0.0)
                if fr["side"] == "BUY":
                    cash -= px * sz + fee
                else:
                    cash += px * sz - fee
                realized_total += rz
                if int(fr["ts"]) >= day_start:
                    realized_today += rz
        else:
            cash = starting_cash
            realized_total = 0.0
            realized_today = 0.0

        peak = max(starting_cash, self.peak_equity(mode))
        return {
            "positions": positions,
            "cash": round(cash, 6),
            "realized_pnl": round(realized_total, 6),
            "realized_pnl_today": round(realized_today, 6),
            "peak_equity": round(peak, 6),
        }

    def open_positions(self, mode: str | None = None) -> list[sqlite3.Row]:
        """פוזיציות פתוחות — לקריאה בלבד, לצורכי status/דוחות."""
        q = "SELECT * FROM positions WHERE size > 0 AND closed_at IS NULL"
        args: tuple = ()
        if mode:
            q += " AND mode = ?"
            args = (mode,)
        with self.tx() as c:
            return list(c.execute(q + " ORDER BY opened_at", args))

    def fills_since(self, ts: int, mode: str | None = None) -> list[sqlite3.Row]:
        q = "SELECT * FROM fills WHERE ts >= ?"
        args: list = [ts]
        if mode:
            q += " AND mode = ?"
            args.append(mode)
        with self.tx() as c:
            return list(c.execute(q + " ORDER BY ts", args))

    def closed_trades(self) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM positions WHERE closed_at IS NOT NULL ORDER BY closed_at"
        ).fetchall()

    def event_log(self, since_ts: int = 0, limit: int = 200) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM events WHERE ts >= ? ORDER BY ts DESC LIMIT ?", (since_ts, limit)
        ).fetchall()

    # ------------------------------------------------------------------
    #  חדשות, תוצאות אותות בזמן אמת, למידה עצמית וגרפים
    # ------------------------------------------------------------------
    def upsert_news(self, items: list[dict[str, Any]]) -> int:
        if not items:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO news_items(id, ts, title, source, url, query, category,
                       sentiment, impact, matched_tokens)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     ts = MAX(news_items.ts, excluded.ts),
                     sentiment = excluded.sentiment,
                     impact = excluded.impact,
                     matched_tokens = CASE
                       WHEN excluded.matched_tokens != '' THEN excluded.matched_tokens
                       ELSE news_items.matched_tokens
                     END""",
                [
                    (
                        str(it["id"]),
                        int(it["ts"]),
                        str(it["title"]),
                        str(it.get("source", "")),
                        str(it.get("url", "")),
                        str(it.get("query", "")),
                        str(it.get("category", "macro")),
                        float(it.get("sentiment", 0.0)),
                        float(it.get("impact", 0.0)),
                        str(it.get("matched_tokens", "")),
                    )
                    for it in items
                ],
            )
        return len(items)

    def recent_news(self, hours: float = 48.0, limit: int = 80) -> list[sqlite3.Row]:
        since = int(datetime.now(tz=timezone.utc).timestamp() - hours * 3600)
        return self._conn.execute(
            "SELECT * FROM news_items WHERE ts >= ? ORDER BY ts DESC LIMIT ?",
            (since, limit),
        ).fetchall()

    def pending_signals_for_outcome(self, min_age_hours: float = 6.0, limit: int = 800) -> list[sqlite3.Row]:
        cutoff = int(datetime.now(tz=timezone.utc).timestamp() - min_age_hours * 3600)
        return self._conn.execute(
            """SELECT s.* FROM signals s
               LEFT JOIN signal_outcomes o ON o.signal_id = s.id
               WHERE s.ts <= ?
                 AND s.market_price IS NOT NULL
                 AND (o.signal_id IS NULL OR o.price_48h IS NULL)
               ORDER BY (o.signal_id IS NULL) DESC, s.ts ASC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()

    def nearest_tick_price(self, token_id: str, target_ts: int, window_sec: int = 7200) -> float | None:
        row = self._conn.execute(
            """SELECT price FROM ticks
               WHERE token_id=? AND ts BETWEEN ? AND ?
               ORDER BY ABS(ts - ?) ASC LIMIT 1""",
            (token_id, target_ts - window_sec, target_ts + window_sec, target_ts),
        ).fetchone()
        if row:
            return float(row["price"])
        brow = self._conn.execute(
            """SELECT COALESCE(mid, best_bid) AS p FROM books
               WHERE token_id=? AND ts BETWEEN ? AND ? AND COALESCE(mid, best_bid) IS NOT NULL
               ORDER BY ABS(ts - ?) ASC LIMIT 1""",
            (token_id, target_ts - window_sec, target_ts + window_sec, target_ts),
        ).fetchone()
        return float(brow["p"]) if brow and brow["p"] is not None else None

    def upsert_signal_outcome(self, row: dict[str, Any]) -> None:
        with self.tx() as c:
            c.execute(
                """INSERT INTO signal_outcomes(
                       signal_id, token_id, ts, direction, entry_price, fair_price, edge,
                       z_score, sector, news_impact, price_6h, price_24h, price_48h,
                       realized_6h, realized_24h, realized_48h, evaluated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(signal_id) DO UPDATE SET
                     price_6h = COALESCE(excluded.price_6h, signal_outcomes.price_6h),
                     price_24h = COALESCE(excluded.price_24h, signal_outcomes.price_24h),
                     price_48h = COALESCE(excluded.price_48h, signal_outcomes.price_48h),
                     realized_6h = COALESCE(excluded.realized_6h, signal_outcomes.realized_6h),
                     realized_24h = COALESCE(excluded.realized_24h, signal_outcomes.realized_24h),
                     realized_48h = COALESCE(excluded.realized_48h, signal_outcomes.realized_48h),
                     news_impact = MAX(signal_outcomes.news_impact, excluded.news_impact),
                     evaluated_at = excluded.evaluated_at""",
                (
                    int(row["signal_id"]),
                    str(row["token_id"]),
                    int(row["ts"]),
                    str(row.get("direction") or ""),
                    row.get("entry_price"),
                    row.get("fair_price"),
                    row.get("edge"),
                    row.get("z_score"),
                    str(row.get("sector") or ""),
                    float(row.get("news_impact") or 0.0),
                    row.get("price_6h"),
                    row.get("price_24h"),
                    row.get("price_48h"),
                    row.get("realized_6h"),
                    row.get("realized_24h"),
                    row.get("realized_48h"),
                    int(row.get("evaluated_at") or datetime.now(tz=timezone.utc).timestamp()),
                ),
            )

    def signal_outcome_stats(self, days: int = 30) -> dict[str, Any]:
        since = int(datetime.now(tz=timezone.utc).timestamp() - days * 86400)
        rows = list(self._conn.execute(
            """SELECT * FROM signal_outcomes
               WHERE ts >= ? AND (realized_6h IS NOT NULL OR realized_24h IS NOT NULL OR realized_48h IS NOT NULL)""",
            (since,),
        ).fetchall())

        def _agg(subset: list[sqlite3.Row]) -> dict[str, Any]:
            r6 = [float(r["realized_6h"]) for r in subset if r["realized_6h"] is not None]
            r24 = [float(r["realized_24h"]) for r in subset if r["realized_24h"] is not None]
            r48 = [float(r["realized_48h"]) for r in subset if r["realized_48h"] is not None]
            latest = []
            for r in subset:
                v = r["realized_48h"] if r["realized_48h"] is not None else (
                    r["realized_24h"] if r["realized_24h"] is not None else r["realized_6h"]
                )
                if v is not None:
                    latest.append(float(v))
            wins_latest = sum(1 for v in latest if v > 0)
            return {
                "n": len(subset),
                "n_6h": len(r6),
                "n_24h": len(r24),
                "n_48h": len(r48),
                "hit_24h_pct": round(sum(1 for v in r24 if v > 0) / len(r24) * 100, 1) if r24 else None,
                "mean_24h": round(sum(r24) / len(r24), 4) if r24 else None,
                "hit_48h_pct": round(sum(1 for v in r48 if v > 0) / len(r48) * 100, 1) if r48 else None,
                "mean_48h": round(sum(r48) / len(r48), 4) if r48 else None,
                "hit_latest_pct": round(wins_latest / len(latest) * 100, 1) if latest else None,
                "mean_latest": round(sum(latest) / len(latest), 4) if latest else None,
            }

        actionable = [r for r in rows if (r["direction"] or "") in {"LONG", "BUY"}]
        buckets: dict[str, list[sqlite3.Row]] = {"1.5-2.0": [], "2.0-3.0": [], "3.0+": []}
        by_sector: dict[str, list[sqlite3.Row]] = {}
        with_news: list[sqlite3.Row] = []
        quiet_news: list[sqlite3.Row] = []
        for r in actionable:
            az = abs(float(r["z_score"] or 0.0))
            if az >= 3.0:
                buckets["3.0+"].append(r)
            elif az >= 2.0:
                buckets["2.0-3.0"].append(r)
            else:
                buckets["1.5-2.0"].append(r)
            sec = str(r["sector"] or "other")
            by_sector.setdefault(sec, []).append(r)
            if float(r["news_impact"] or 0.0) >= 0.5:
                with_news.append(r)
            else:
                quiet_news.append(r)

        return {
            "total_evaluated": len(rows),
            "actionable": _agg(actionable),
            "by_z_bucket": {k: _agg(v) for k, v in buckets.items() if v},
            "by_sector": {k: _agg(v) for k, v in sorted(by_sector.items())},
            "by_news": {
                "quiet": _agg(quiet_news),
                "news_catalyst": _agg(with_news),
            },
        }

    def record_learning_run(
        self,
        *,
        mode: str,
        baseline_oos: float,
        candidate_oos: float,
        consistency: float,
        oos_trades: int,
        baseline_cfg: dict[str, Any],
        candidate_cfg: dict[str, Any],
        applied: bool,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> int:
        with self.tx() as c:
            cur = c.execute(
                """INSERT INTO learning_runs(
                       ts, mode, baseline_oos, candidate_oos, consistency, oos_trades,
                       baseline_cfg, candidate_cfg, applied, summary, details)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    int(datetime.now(tz=timezone.utc).timestamp()),
                    mode,
                    round(float(baseline_oos), 4),
                    round(float(candidate_oos), 4),
                    round(float(consistency), 4),
                    int(oos_trades),
                    json.dumps(baseline_cfg, ensure_ascii=False),
                    json.dumps(candidate_cfg, ensure_ascii=False),
                    1 if applied else 0,
                    summary,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid or 0)

    def recent_learning_runs(self, limit: int = 15) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM learning_runs ORDER BY ts DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": int(r["id"]),
                "ts": int(r["ts"]),
                "mode": r["mode"],
                "baseline_oos": r["baseline_oos"],
                "candidate_oos": r["candidate_oos"],
                "consistency": r["consistency"],
                "oos_trades": r["oos_trades"],
                "baseline_cfg": json.loads(r["baseline_cfg"] or "{}"),
                "candidate_cfg": json.loads(r["candidate_cfg"] or "{}"),
                "applied": bool(r["applied"]),
                "summary": r["summary"],
                "details": json.loads(r["details"] or "{}"),
            })
        return out

    def chart_candidates(self, mode: str = "paper", limit: int = 16) -> list[dict[str, Any]]:
        """רשימת שווקים זמינים לגרף חי — פוזיציות פתוחות קודם, ואז טוקנים עם סיגנל/טיקים."""
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for r in self.open_positions(mode):
            tid = str(r["token_id"])
            seen.add(tid)
            items.append({
                "token_id": tid,
                "question": str(r["question"] or tid[:16]),
                "open": True,
                "avg_price": float(r["avg_price"] or 0.0),
                "stop_price": r["stop_price"],
                "target_price": r["target_price"],
            })
        rows = self._conn.execute(
            """SELECT t.token_id, COUNT(*) AS cnt, MAX(t.ts) AS last_ts,
                      COALESCE(
                        NULLIF((SELECT mi.question FROM market_intel mi WHERE mi.token_id=t.token_id LIMIT 1), ''),
                        NULLIF((SELECT p.question FROM positions p WHERE p.token_id=t.token_id LIMIT 1), ''),
                        ''
                      ) AS q,
                      (SELECT s.reason FROM signals s WHERE s.token_id=t.token_id ORDER BY s.id DESC LIMIT 1) AS last_sig
               FROM ticks t
               GROUP BY t.token_id
               HAVING cnt >= 6
               ORDER BY last_ts DESC, cnt DESC
               LIMIT ?""",
            (limit + len(seen),),
        ).fetchall()
        for r in rows:
            tid = str(r["token_id"])
            if tid in seen:
                continue
            seen.add(tid)
            items.append({
                "token_id": tid,
                "question": str(r["q"] or r["last_sig"] or tid[:18]),
                "open": False,
                "points": int(r["cnt"]),
            })
            if len(items) >= limit:
                break
        return items

    def token_chart_series(self, token_id: str, limit: int = 160) -> dict[str, Any]:
        ticks = list(reversed(self._conn.execute(
            "SELECT ts, price FROM ticks WHERE token_id=? ORDER BY ts DESC LIMIT ?",
            (token_id, limit),
        ).fetchall()))
        books = list(reversed(self._conn.execute(
            """SELECT ts, mid, best_bid, best_ask, bid_depth, ask_depth, imbalance
               FROM books WHERE token_id=? ORDER BY ts DESC LIMIT 30""",
            (token_id,),
        ).fetchall()))
        sigs = list(reversed(self._conn.execute(
            """SELECT ts, direction, score, fair_price, market_price, edge, reason, features
               FROM signals WHERE token_id=? ORDER BY id DESC LIMIT 20""",
            (token_id,),
        ).fetchall()))
        pos = self._conn.execute(
            "SELECT * FROM positions WHERE token_id=? AND size > 0 AND closed_at IS NULL",
            (token_id,),
        ).fetchone()
        intel = self._conn.execute(
            "SELECT * FROM market_intel WHERE token_id=? ORDER BY updated_at DESC LIMIT 1",
            (token_id,),
        ).fetchone()
        return {
            "token_id": token_id,
            "question": (pos["question"] if pos else (intel["question"] if intel else "")),
            "ticks": [{"ts": int(r["ts"]), "price": round(float(r["price"]), 4)} for r in ticks],
            "books": [
                {
                    "ts": int(r["ts"]),
                    "mid": r["mid"],
                    "best_bid": r["best_bid"],
                    "best_ask": r["best_ask"],
                    "bid_depth": r["bid_depth"],
                    "ask_depth": r["ask_depth"],
                    "imbalance": r["imbalance"],
                }
                for r in books
            ],
            "signals": [
                {
                    "ts": int(r["ts"]),
                    "direction": r["direction"],
                    "score": r["score"],
                    "fair_price": r["fair_price"],
                    "market_price": r["market_price"],
                    "edge": r["edge"],
                    "reason": r["reason"],
                }
                for r in sigs
            ],
            "position": {
                "question": pos["question"],
                "avg_price": pos["avg_price"],
                "stop_price": pos["stop_price"],
                "target_price": pos["target_price"],
                "size": pos["size"],
            } if pos else None,
            "intel": dict(intel) if intel else None,
        }

    # ------------------------------------------------------------------
    #  מודיעין שווקים רב-ממדי (market_intel) ויומן אוטופיילוט
    # ------------------------------------------------------------------
    def upsert_market_intel(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        with self.tx() as c:
            c.executemany(
                """INSERT INTO market_intel(
                       condition_id, token_id, question, sector, price, spread,
                       bid_depth, ask_depth, imbalance, volume_24h, volume_ratio,
                       chg_1h, chg_6h, chg_24h, z_score, edge_net,
                       rsi, setup_tier, microprice,
                       news_count, news_impact, hours_left, status, reason, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(condition_id) DO UPDATE SET
                     token_id=excluded.token_id,
                     question=excluded.question,
                     sector=excluded.sector,
                     price=excluded.price,
                     spread=excluded.spread,
                     bid_depth=excluded.bid_depth,
                     ask_depth=excluded.ask_depth,
                     imbalance=excluded.imbalance,
                     volume_24h=excluded.volume_24h,
                     volume_ratio=excluded.volume_ratio,
                     chg_1h=excluded.chg_1h,
                     chg_6h=excluded.chg_6h,
                     chg_24h=excluded.chg_24h,
                     z_score=excluded.z_score,
                     edge_net=excluded.edge_net,
                     rsi=excluded.rsi,
                     setup_tier=excluded.setup_tier,
                     microprice=excluded.microprice,
                     news_count=excluded.news_count,
                     news_impact=excluded.news_impact,
                     hours_left=excluded.hours_left,
                     status=excluded.status,
                     reason=excluded.reason,
                     updated_at=excluded.updated_at""",
                [
                    (
                        str(r["condition_id"]),
                        str(r["token_id"]),
                        str(r["question"]),
                        str(r.get("sector") or "other"),
                        r.get("price"),
                        r.get("spread"),
                        float(r.get("bid_depth") or 0.0),
                        float(r.get("ask_depth") or 0.0),
                        float(r.get("imbalance") or 0.0),
                        float(r.get("volume_24h") or 0.0),
                        float(r.get("volume_ratio") or 1.0),
                        r.get("chg_1h"),
                        r.get("chg_6h"),
                        r.get("chg_24h"),
                        r.get("z_score"),
                        r.get("edge_net"),
                        r.get("rsi"),
                        str(r.get("setup_tier") or "B"),
                        r.get("microprice"),
                        int(r.get("news_count") or 0),
                        float(r.get("news_impact") or 0.0),
                        r.get("hours_left"),
                        str(r.get("status") or "WATCH"),
                        str(r.get("reason") or "")[:120],
                        int(r.get("updated_at") or datetime.now(tz=timezone.utc).timestamp()),
                    )
                    for r in rows
                ],
            )
        return len(rows)

    def recent_market_intel(self, limit: int = 60) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT * FROM market_intel
               ORDER BY
                 CASE status
                   WHEN 'OPEN' THEN 0
                   WHEN 'BUY' THEN 1
                   WHEN 'CATALYST_BLOCK' THEN 2
                   ELSE 3
                 END,
                 ABS(COALESCE(z_score, 0)) DESC,
                 volume_24h DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def record_autopilot_run(
        self, task: str, status: str, summary: str, details: dict[str, Any] | None = None
    ) -> int:
        with self.tx() as c:
            cur = c.execute(
                "INSERT INTO autopilot_runs(ts, task, status, summary, details) VALUES (?,?,?,?,?)",
                (
                    int(datetime.now(tz=timezone.utc).timestamp()),
                    task,
                    status,
                    summary,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
            return int(cur.lastrowid or 0)

    def recent_autopilot_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM autopilot_runs ORDER BY ts DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": int(r["id"]),
                "ts": int(r["ts"]),
                "task": r["task"],
                "status": r["status"],
                "summary": r["summary"],
                "details": json.loads(r["details"] or "{}"),
            })
        return out
