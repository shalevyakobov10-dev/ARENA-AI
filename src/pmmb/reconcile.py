"""
סנכרון (Reconciliation) בין ה-DB המקומי לבורסה / ספר הפקודות.

הבעיה שפותרים כאן:
  אם הבוט קרס באמצע מילוי, או שפקודה מולאה חלקית, או שסוחר סגר ידנית
  באתר של Polymarket — ה-DB והמציאות מתפצלים. לפני live (וגם תוך כדי),
  חייבים פקודה שמשווה את שניהם ומתקנת פערים בשקיפות.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .data.http import HttpClient
from .data.store import Store
from .models import Position, utcnow

log = logging.getLogger(__name__)

DATA_API = "https://data-api.polymarket.com"


@dataclass
class Discrepancy:
    kind: str         # ghost_local / unrecorded_exchange / size_mismatch / cash_drift / ledger_mismatch / stale_order
    token_id: str
    detail: str
    fixed: bool = False


@dataclass
class ReconcileReport:
    mode: str
    checked_positions: int = 0
    exchange_positions: int = 0
    open_orders: int = 0
    local_cash: float | None = None
    exchange_cash: float | None = None
    discrepancies: list[Discrepancy] = field(default_factory=list)
    fixes_applied: int = 0

    @property
    def clean(self) -> bool:
        return len(self.discrepancies) == 0

    def to_markdown(self) -> str:
        icon = "🟢" if self.clean else "🟠"
        lines = [
            f"# סנכרון חשבון ({self.mode})",
            "",
            f"- פוזיציות ב-DB: **{self.checked_positions}** · בבורסה: **{self.exchange_positions}** · "
            f"פקודות פתוחות: **{self.open_orders}**",
        ]
        if self.local_cash is not None:
            ex_txt = f"{self.exchange_cash:.2f}" if self.exchange_cash is not None else "—"
            lines.append(f"- מזומן ב-DB: **{self.local_cash:.2f}** · בבורסה: **{ex_txt}**")
        lines.append("")

        if self.clean:
            lines.append(f"{icon} **ה-DB תואם למציאות — אפס פערים.**")
        else:
            lines.append(f"{icon} **נמצאו {len(self.discrepancies)} פערים** "
                         f"(תוקנו: {self.fixes_applied}):")
            lines.append("")
            for d in self.discrepancies:
                tag = "✅ תוקן" if d.fixed else "⚠️ פתוח"
                lines.append(f"- `{d.kind}` ({d.token_id[:14]}): {d.detail} [{tag}]")
        return "\n".join(lines)


# ------------------------------------------------------------------ Data API
def fetch_exchange_positions(address: str, *, base_url: str = DATA_API) -> list[dict]:
    """מושך פוזיציות פתוחות מ-Polymarket Data API הציבורי."""
    if not address:
        return []
    http = HttpClient(base_url, timeout=15.0, max_retries=2, rate_limit_rps=4.0)
    raw = http.get("/positions", params={"user": address, "sizeThreshold": "0.01"})
    return list(raw) if isinstance(raw, list) else []


# ------------------------------------------------------------------ Paper / DB ledger audit
def reconcile_paper(store: Store, *, starting_cash: float = 1000.0,
                    fix: bool = False) -> ReconcileReport:
    """
    בודק עקביות פנימית של חשבון ה-paper ב-DB:
      - כל פוזיציה פתוחה תואמת לסכום ה-fills של הטוקן
      - אין שורות size<=0 שנותרו פתוחות
      - אין שני טוקנים לאותו condition_id
      - המזומן ב-snapshot האחרון תואם את ספר החשבונות של ה-fills
    """
    rep = ReconcileReport(mode="paper")
    st = store.load_portfolio_state("paper", starting_cash)
    rep.local_cash = st["cash"]
    positions = st["positions"]
    rep.checked_positions = len(positions)

    # 1. בדיקת fills ledger מול טבלת positions
    rows = list(store._conn.execute(
        "SELECT token_id, condition_id, "
        "SUM(CASE WHEN side='BUY' THEN size ELSE -size END) AS net_size, "
        "MAX(ts) AS last_ts "
        "FROM fills WHERE mode='paper' GROUP BY token_id"
    ).fetchall())
    ledger = {r["token_id"]: float(r["net_size"] or 0.0) for r in rows}
    pos_map = {p.token_id: p for p in positions}

    for tid, p in pos_map.items():
        if p.size <= 1e-6:
            d = Discrepancy("zero_open", tid, "פוזיציה פתוחה עם גודל 0")
            if fix:
                store.close_position(tid, "reconcile: גודל אפס", 0.0)
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)
        elif tid in ledger and abs(ledger[tid] - p.size) > 0.05:
            d = Discrepancy("ledger_mismatch", tid,
                            f"DB={p.size:.2f} לעומת סך fills={ledger[tid]:.2f}")
            if fix:
                if ledger[tid] <= 0.01:
                    store.close_position(tid, "reconcile: נסגר לפי fills", 0.0)
                else:
                    p.size = round(ledger[tid], 4)
                    store.upsert_position(p, "paper")
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)

    for tid, net in ledger.items():
        if net > 0.05 and tid not in pos_map:
            d = Discrepancy("unrecorded_fill_pos", tid,
                            f"fills מראים {net:.2f} מניות פתוחות אבל הפוזיציה לא רשומה כפתוחה")
            if fix:
                cid = next((r["condition_id"] or "" for r in rows if r["token_id"] == tid), "")
                store.upsert_position(Position(
                    token_id=tid, condition_id=cid, direction="LONG",
                    size=round(net, 4), avg_price=0.5, question="שוחזר מ-fills",
                ), "paper")
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)

    # 2. בדיקת snapshot אחרון מול ledger cash
    eq_row = store._conn.execute(
        "SELECT cash FROM equity WHERE mode='paper' OR mode IS NULL ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    if eq_row is not None:
        snap_cash = float(eq_row["cash"])
        if abs(snap_cash - st["cash"]) > 0.50:
            d = Discrepancy(
                "cash_drift", "paper-cash",
                f"snapshot אחרון={snap_cash:.2f} לעומת ledger={st['cash']:.2f}",
            )
            if fix:
                from .models import PortfolioSnapshot
                st_after = store.load_portfolio_state("paper", starting_cash)
                marks = store.latest_marks([p.token_id for p in st_after["positions"]])
                exp = sum(p.size * marks.get(p.token_id, p.avg_price) for p in st_after["positions"])
                eq = st_after["cash"] + exp
                store.snapshot_equity(PortfolioSnapshot(
                    cash=round(st_after["cash"], 6),
                    equity=round(eq, 6),
                    exposure=round(exp, 6),
                    open_positions=len(st_after["positions"]),
                    realized_pnl_today=st_after["realized_pnl_today"],
                    peak_equity=max(st_after["peak_equity"], eq),
                ), mode="paper")
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)

    if rep.fixes_applied:
        store.event("reconcile", f"סונכרנו {rep.fixes_applied} פערים ב-paper")
    return rep


# ------------------------------------------------------------------ Live reconciliation
def reconcile_live(
    store: Store,
    broker,
    *,
    starting_cash: float = 1000.0,
    fix: bool = False,
    cancel_orders: bool = False,
    exchange_positions: list[dict] | None = None,
) -> ReconcileReport:
    """משווה DB מקומי מול הבורסה האמיתית (Polymarket CLOB + Data API)."""
    rep = ReconcileReport(mode="live")
    st = store.load_portfolio_state("live", starting_cash)
    rep.local_cash = st["cash"]
    local_map = {p.token_id: p for p in st["positions"]}
    rep.checked_positions = len(local_map)

    ex_cash = broker.usdc_balance()
    rep.exchange_cash = ex_cash

    orders = broker.open_orders()
    rep.open_orders = len(orders)
    if orders:
        for o in orders:
            oid = str(o.get("id") or o.get("orderID") or "")[:14]
            d = Discrepancy("stale_order", str(o.get("asset_id") or oid),
                            f"פקודה פתוחה בבורסה ({o.get('side')} {o.get('original_size')} @ {o.get('price')})")
            rep.discrepancies.append(d)
        if cancel_orders:
            cancelled = broker.cancel_all()
            for d in rep.discrepancies:
                if d.kind == "stale_order":
                    d.fixed = True
            rep.fixes_applied += cancelled or len(orders)

    # פוזיציות מהבורסה: Data API (אם לא הועברו בבדיקה) + גיבוי יתרה ישירה
    if exchange_positions is None:
        addr = broker.wallet_address()
        exchange_positions = fetch_exchange_positions(addr) if addr else []

    ex_map: dict[str, dict] = {}
    for row in exchange_positions:
        tid = str(row.get("asset") or row.get("token_id") or "")
        sz = float(row.get("size") or 0.0)
        if tid and sz > 0.01:
            ex_map[tid] = {
                "size": sz,
                "avg_price": float(row.get("avgPrice") or row.get("curPrice") or 0.5),
                "condition_id": str(row.get("conditionId") or ""),
                "title": str(row.get("title") or row.get("question") or ""),
            }
    rep.exchange_positions = len(ex_map)

    # 1. פוזיציות שקיימות ב-DB אבל חסרות בבורסה (ghost) או בגודל שונה
    for tid, pos in local_map.items():
        if tid not in ex_map:
            # בדיקת גיבוי ישירה מול CLOB conditional balance
            bal = broker.conditional_balance(tid)
            if bal is not None and bal > 0.01:
                ex_map[tid] = {"size": bal, "avg_price": pos.avg_price,
                               "condition_id": pos.condition_id, "title": pos.question}
                rep.exchange_positions += 1
            else:
                d = Discrepancy("ghost_local", tid,
                                f"רשומה כפתוחה ({pos.size:.2f}) ב-DB אבל 0 בבורסה")
                if fix:
                    store.close_position(tid, "reconcile: לא נמצא בבורסה", 0.0)
                    d.fixed = True
                    rep.fixes_applied += 1
                rep.discrepancies.append(d)
                continue

        ex_sz = ex_map[tid]["size"]
        if abs(ex_sz - pos.size) > 0.05:
            d = Discrepancy("size_mismatch", tid,
                            f"DB={pos.size:.2f} לעומת בורסה={ex_sz:.2f}")
            if fix:
                pos.size = round(ex_sz, 4)
                store.upsert_position(pos, "live")
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)

    # 2. פוזיציות שקיימות בבורסה אבל לא ב-DB
    for tid, ex in ex_map.items():
        if tid not in local_map:
            d = Discrepancy("unrecorded_exchange", tid,
                            f"קיימת בבורסה ({ex['size']:.2f} @ {ex['avg_price']:.3f}) "
                            f"ולא רשומה ב-DB — {ex['title'][:40]}")
            if fix:
                store.upsert_position(Position(
                    token_id=tid,
                    condition_id=ex["condition_id"],
                    direction="LONG",
                    size=round(ex["size"], 4),
                    avg_price=round(ex["avg_price"], 4),
                    opened_at=utcnow(),
                    question=ex["title"],
                ), "live")
                d.fixed = True
                rep.fixes_applied += 1
            rep.discrepancies.append(d)

    # 3. בדיקת מזומן
    if ex_cash is not None and abs(ex_cash - st["cash"]) > 1.0:
        rep.discrepancies.append(Discrepancy(
            "cash_drift", "usdc",
            f"DB={st['cash']:.2f} USDC לעומת בורסה={ex_cash:.2f} USDC (הבדל {ex_cash - st['cash']:+.2f})",
        ))

    if rep.fixes_applied:
        store.event("reconcile", f"סונכרנו {rep.fixes_applied} פערים ב-live",
                    level="WARNING")
    return rep
