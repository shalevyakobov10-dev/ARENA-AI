"""
דוח יומי — מה קרה בבוט ב-24 השעות האחרונות, בשפה של בן אדם.

מיועד להרצה אוטומטית (cron / systemd timer) כדי שאפשר יהיה להריץ paper
לאורך שבועות בלי לשבת על הלוג. כל הנתונים מה-DB — הבוט עצמו לא צריך לרוץ.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .data.store import Store

log = logging.getLogger(__name__)


@dataclass
class DailyReport:
    since: datetime
    until: datetime
    signals: int = 0
    entries: int = 0
    exits: int = 0
    errors: int = 0
    realized_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    best_market: str = ""
    best_pnl: float = 0.0
    worst_market: str = ""
    worst_pnl: float = 0.0
    equity_start: float | None = None
    equity_end: float | None = None
    open_positions: list[dict] = field(default_factory=list)
    stale_positions: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        n = self.wins + self.losses
        return self.wins / n * 100 if n else 0.0

    @property
    def equity_change_pct(self) -> float:
        if not self.equity_start:
            return 0.0
        return (self.equity_end - self.equity_start) / self.equity_start * 100

    def to_markdown(self) -> str:
        d = self.until.strftime("%Y-%m-%d")
        lines = [
            f"# דוח יומי — {d}",
            "",
            f"חלון: {self.since.strftime('%d/%m %H:%M')} → {self.until.strftime('%d/%m %H:%M')} UTC",
            "",
            "## תנועה",
            "",
            f"- סיגנלים: **{self.signals}** · כניסות: **{self.entries}** · יציאות: **{self.exits}**",
            f"- רווח ממומש: **{self.realized_pnl:+.2f} USDC** "
            f"(win rate {self.win_rate:.0f}% על {self.wins + self.losses} עסקאות)",
        ]
        if self.equity_start is not None and self.equity_end is not None:
            lines.append(
                f"- הון: {self.equity_start:.2f} → **{self.equity_end:.2f}** "
                f"({self.equity_change_pct:+.2f}%)"
            )

        if self.exits:
            lines += [
                "",
                "## העסקאות",
                "",
                f"- הטובה: {self.best_market[:50]} **{self.best_pnl:+.2f}**",
                f"- הגרועה: {self.worst_market[:50]} **{self.worst_pnl:+.2f}**",
            ]

        if self.open_positions:
            lines += ["", "## פוזיציות פתוחות", "",
                      "| שוק | כיוון | גודל | כניסה | נפתח |", "|---|---|---|---|---|"]
            for p in self.open_positions:
                opened = datetime.fromtimestamp(p["opened_at"], tz=timezone.utc)
                age_h = (self.until - opened).total_seconds() / 3600
                lines.append(
                    f"| {(p['question'] or p['token_id'])[:40]} | {p['direction']} "
                    f"| {p['size']:.2f} | {p['avg_price']:.3f} | {age_h:.0f}ש' |"
                )

        if self.stale_positions:
            lines += ["", "## ⚠️ פוזיציות תקועות", ""]
            for p in self.stale_positions:
                lines.append(f"- {(p['question'] or p['token_id'])[:50]} — פתוחה "
                             f"{p['age_hours']:.0f} שעות (אופק מתוכנן 48)")

        if self.warnings:
            lines += ["", "## התראות", ""] + [f"- {w}" for w in self.warnings]

        lines += ["", "---", "> הדוח נוצר אוטומטית מה-DB. paper בלבד — לא ביצועים אמיתיים."]
        return "\n".join(lines)


def build_daily_report(
    store: Store,
    *,
    hours: int = 24,
    now: datetime | None = None,
    planned_horizon_hours: float = 48.0,
    starting_cash: float = 1000.0,
    mode: str | None = None,
) -> DailyReport:
    now = now or datetime.now(tz=timezone.utc)
    since = now - timedelta(hours=hours)
    ts_since, ts_now = int(since.timestamp()), int(now.timestamp())
    conn = store._conn

    rep = DailyReport(since=since, until=now)

    rep.signals = conn.execute(
        "SELECT COUNT(*) c FROM signals WHERE ts >= ? AND ts <= ?", (ts_since, ts_now)
    ).fetchone()["c"]

    m_clause = " AND mode = ?" if mode else ""
    m_args: tuple = (mode,) if mode else ()

    conn_entries = conn.execute(
        f"SELECT COUNT(*) c FROM fills WHERE ts >= ? AND ts <= ? AND side='BUY'{m_clause}",
        (ts_since, ts_now, *m_args),
    ).fetchone()["c"]
    rep.entries = conn_entries
    rep.exits = conn.execute(
        f"SELECT COUNT(*) c FROM fills WHERE ts >= ? AND ts <= ? AND side='SELL'{m_clause}",
        (ts_since, ts_now, *m_args),
    ).fetchone()["c"]

    rep.errors = conn.execute(
        "SELECT COUNT(*) c FROM events WHERE ts >= ? AND ts <= ? AND level IN ('ERROR','CRITICAL')",
        (ts_since, ts_now),
    ).fetchone()["c"]

    # רווח ממומש נלקח מה-fills (כולל יציאות חלקיות ועסקאות חוזרות על אותו טוקן)
    rep.realized_pnl = float(conn.execute(
        f"SELECT COALESCE(SUM(realized),0) s FROM fills WHERE ts >= ? AND ts <= ?{m_clause}",
        (ts_since, ts_now, *m_args),
    ).fetchone()["s"] or 0.0)

    closed = conn.execute(
        f"SELECT * FROM positions WHERE closed_at >= ? AND closed_at <= ?{m_clause} ORDER BY closed_at",
        (ts_since, ts_now, *m_args),
    ).fetchall()
    sell_trades = conn.execute(
        f"""SELECT f.token_id, f.realized, COALESCE(p.question, '') AS question
            FROM fills f LEFT JOIN positions p ON p.token_id = f.token_id
            WHERE f.ts >= ? AND f.ts <= ? AND f.side='SELL' AND f.realized != 0{m_clause.replace('mode', 'f.mode')}
            ORDER BY f.ts""",
        (ts_since, ts_now, *m_args),
    ).fetchall()

    if len(sell_trades) > len(closed):
        rep.wins = sum(1 for r in sell_trades if (r["realized"] or 0) > 0)
        rep.losses = sum(1 for r in sell_trades if (r["realized"] or 0) <= 0)
        best = max(sell_trades, key=lambda r: r["realized"] or 0)
        worst = min(sell_trades, key=lambda r: r["realized"] or 0)
        rep.best_market, rep.best_pnl = best["question"] or best["token_id"], float(best["realized"] or 0)
        rep.worst_market, rep.worst_pnl = worst["question"] or worst["token_id"], float(worst["realized"] or 0)
    elif closed:
        rep.wins = sum(1 for r in closed if (r["realized_pnl"] or 0) > 0)
        rep.losses = sum(1 for r in closed if (r["realized_pnl"] or 0) <= 0)
        best = max(closed, key=lambda r: r["realized_pnl"] or 0)
        worst = min(closed, key=lambda r: r["realized_pnl"] or 0)
        rep.best_market, rep.best_pnl = best["question"] or best["token_id"], float(best["realized_pnl"] or 0)
        rep.worst_market, rep.worst_pnl = worst["question"] or worst["token_id"], float(worst["realized_pnl"] or 0)

    eq_mode = " AND (mode = ? OR mode IS NULL)" if mode else ""
    eq = conn.execute(
        f"SELECT equity FROM equity WHERE ts >= ?{eq_mode} ORDER BY ts LIMIT 1",
        (ts_since, *m_args),
    ).fetchone()
    if eq:
        rep.equity_start = float(eq["equity"])
    else:
        prev = conn.execute(
            f"SELECT equity FROM equity WHERE 1=1{eq_mode} ORDER BY ts DESC LIMIT 1", m_args
        ).fetchone()
        rep.equity_start = float(prev["equity"]) if prev else starting_cash
    last = conn.execute(
        f"SELECT equity FROM equity WHERE 1=1{eq_mode} ORDER BY ts DESC LIMIT 1", m_args
    ).fetchone()
    rep.equity_end = float(last["equity"]) if last else rep.equity_start

    open_rows = conn.execute(
        f"SELECT * FROM positions WHERE closed_at IS NULL AND size > 0{m_clause}", m_args
    ).fetchall()
    for r in open_rows:
        opened = datetime.fromtimestamp(r["opened_at"], tz=timezone.utc)
        age_h = (now - opened).total_seconds() / 3600
        row = {
            "token_id": r["token_id"], "question": r["question"], "direction": r["direction"],
            "size": r["size"], "avg_price": r["avg_price"], "opened_at": r["opened_at"],
            "age_hours": age_h,
        }
        rep.open_positions.append(row)
        if age_h > planned_horizon_hours * 2:
            rep.stale_positions.append(row)

    # --- התראות ---
    if rep.equity_start and rep.equity_end and rep.equity_change_pct < -5:
        rep.warnings.append(f"הון ירד {rep.equity_change_pct:.1f}% ב-{hours} שעות")
    if rep.errors:
        rep.warnings.append(f"{rep.errors} שגיאות logged — בדוק את events ב-DB")
    if rep.stale_positions:
        rep.warnings.append(f"{len(rep.stale_positions)} פוזיציות פתוחות מעבר לאופק המתוכנן")
    if not rep.signals and not rep.open_positions:
        rep.warnings.append("אין סיגנלים ואין פוזיציות — הבוט אולי לא רץ, או שהשוק שקט")

    return rep


def write_daily_report(rep: DailyReport, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"daily-{rep.until.strftime('%Y%m%d')}.md"
    path.write_text(rep.to_markdown(), encoding="utf-8")
    return path
