"""
אבחון הסיגנל — "האם יש בכלל edge?" לפני שמשפרים משהו.

המודול עונה על שאלה אחת: כשהמנוע אומר LONG/SHORT, מה המחיר עושה ב-N הנרות
הבאים? זה לא בקטסט — אין כאן סטופים, גדלים או עלויות. זו מדידה טהורה של
כוח הניבוי, כדי שנדע אם הבעיה היא בסיגנל או בניהול הסיכון.

מדדים:
  hit_rate  — אחוז המקרים שבהם הכיוון היה נכון (לפני עלויות)
  mean_move — תנועה ממוצעת בנקודות הסתברות לכיוון הסיגנל
  IC        — מתאם (Pearson) בין עוצמת הסיגנל לתנועה העתידית
              IC ≈ 0    → הסיגנל לא שווה כלום
              IC > 0.05 → יש אות, שווה להמשיך
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from .data.clob import Candle
from .models import Market
from .signals.momentum import MomentumEngine

log = logging.getLogger(__name__)


@dataclass
class HorizonStats:
    horizon: int
    n: int = 0
    hits: int = 0
    sum_move: float = 0.0
    xs: list[float] = field(default_factory=list)   # signed score
    ys: list[float] = field(default_factory=list)   # forward move

    @property
    def hit_rate(self) -> float:
        return self.hits / self.n if self.n else 0.0

    @property
    def mean_move(self) -> float:
        return self.sum_move / self.n if self.n else 0.0

    @property
    def ic(self) -> float:
        if len(self.xs) < 30:
            return 0.0
        n = len(self.xs)
        mx = sum(self.xs) / n
        my = sum(self.ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(self.xs, self.ys))
        vx = sum((x - mx) ** 2 for x in self.xs)
        vy = sum((y - my) ** 2 for y in self.ys)
        if vx <= 0 or vy <= 0:
            return 0.0
        return cov / math.sqrt(vx * vy)


@dataclass
class DiagnosticsResult:
    markets: int
    evaluations: int
    signals: int
    horizons: dict[int, HorizonStats]
    by_score: dict[str, HorizonStats]     # פילוח לפי עוצמת סיגנל
    per_market: list[dict]

    def to_markdown(self) -> str:
        lines = [
            "# אבחון כוח ניבוי הסיגנל",
            "",
            f"שווקים: {self.markets} · הרצות סיגנל: {self.evaluations:,} · "
            f"סיגנלים פעילים: {self.signals:,} "
            f"({self.signals / max(self.evaluations, 1) * 100:.1f}%)",
            "",
            "## לפי אופק (נרות קדימה)",
            "",
            "| אופק | דגימות | hit rate | תנועה ממוצעת | IC |",
            "|---|---|---|---|---|",
        ]
        for h in sorted(self.horizons):
            s = self.horizons[h]
            lines.append(
                f"| {h} | {s.n} | {s.hit_rate * 100:.1f}% | {s.mean_move:+.4f} | {s.ic:+.3f} |"
            )
        lines += [
            "",
            "## לפי עוצמת סיגנל (אופק 6)",
            "",
            "| טווח score | דגימות | hit rate | תנועה ממוצעת |",
            "|---|---|---|---|",
        ]
        for label, s in self.by_score.items():
            lines.append(f"| {label} | {s.n} | {s.hit_rate * 100:.1f}% | {s.mean_move:+.4f} |")
        lines += [
            "",
            "> hit rate של 50% = הטלת מטבע. תנועה ממוצעת חייבת לעלות על",
            "> חצי הספרד + החלקה (~0.005-0.01) כדי שהאסטרטגיה תשרוד עלויות.",
        ]
        return "\n".join(lines)


def run_diagnostics(
    engine: MomentumEngine,
    datasets: list[tuple[Market, list[Candle]]],
    *,
    horizons: tuple[int, ...] = (1, 3, 6, 12, 24),
    spread: float = 0.01,
    score_buckets: tuple[tuple[float, float], ...] = ((0.45, 0.55), (0.55, 0.65), (0.65, 1.01)),
) -> DiagnosticsResult:
    max_h = max(horizons)
    stats = {h: HorizonStats(h) for h in horizons}
    bucket_stats = {f"{lo:.2f}-{hi:.2f}": HorizonStats(6) for lo, hi in score_buckets}
    evaluations = 0
    n_signals = 0
    per_market: list[dict] = []

    for market, candles in datasets:
        prices = [c.price for c in candles]
        n = len(prices)
        m_evals = m_signals = m_hits = 0
        m_move = 0.0

        for i in range(engine.min_candles, n - max_h):
            sig = engine.evaluate(market, prices[: i + 1],
                                  market_price=prices[i], spread=spread,
                                  extra={"fee_rate": market.taker_fee_rate})
            evaluations += 1
            m_evals += 1
            if sig.direction == "FLAT":
                continue
            n_signals += 1
            m_signals += 1
            sign = 1.0 if sig.direction == "LONG" else -1.0
            signed_score = sign * sig.score

            for h in horizons:
                fwd = sign * (prices[i + h] - prices[i])
                s = stats[h]
                s.n += 1
                s.sum_move += fwd
                if fwd > 0:
                    s.hits += 1
                s.xs.append(signed_score)
                s.ys.append(fwd)
                if h == 6:
                    m_hits += 1 if fwd > 0 else 0
                    m_move += fwd

            for (lo, hi), label in zip(score_buckets, bucket_stats):
                if lo <= sig.score < hi:
                    fwd6 = sign * (prices[i + 6] - prices[i])
                    b = bucket_stats[label]
                    b.n += 1
                    b.sum_move += fwd6
                    if fwd6 > 0:
                        b.hits += 1
                    break

        per_market.append({
            "slug": market.slug,
            "evaluations": m_evals,
            "signals": m_signals,
            "hit_rate_6": round(m_hits / m_signals * 100, 1) if m_signals else None,
            "mean_move_6": round(m_move / m_signals, 4) if m_signals else None,
        })

    return DiagnosticsResult(
        markets=len(datasets),
        evaluations=evaluations,
        signals=n_signals,
        horizons=stats,
        by_score=bucket_stats,
        per_market=per_market,
    )


def write_diagnostics(result: DiagnosticsResult, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "diagnostics.md"
    path.write_text(result.to_markdown(), encoding="utf-8")
    return path


# ======================================================================
#  כיול צפי מול מציאות
# ======================================================================
@dataclass
class CalibrationRow:
    label: str
    n: int
    predicted: float        # צפי ממוצע (fair - market)
    realized: float         # תנועה שהתממשה באופק
    hit_rate: float
    bias_ratio: float       # predicted / realized  (1.0 = מכויל)


@dataclass
class CalibrationResult:
    horizon_hours: float
    min_z: float | None
    rows: list[CalibrationRow]
    suggested_ratio: float
    current_ratio: float

    def to_markdown(self) -> str:
        lines = [
            "# כיול הצפי מול המציאות",
            "",
            f"אופק: {self.horizon_hours:g} שעות · יחס נוכחי: {self.current_ratio:g}",
            "",
            "| קבוצה | דגימות | צפי ממוצע | התממש | hit | צפי/מציאות |",
            "|---|---|---|---|---|---|",
        ]
        for r in self.rows:
            lines.append(
                f"| {r.label} | {r.n} | {r.predicted:+.4f} | {r.realized:+.4f} "
                f"| {r.hit_rate * 100:.0f}% | {r.bias_ratio:.2f}× |"
            )
        lines += [
            "",
            f"**יחס מומלץ לפי הכיול: {self.suggested_ratio:.2f}** "
            f"(מול {self.current_ratio:g} בקונפיג)",
            "",
            "> אם `צפי/מציאות` גדול מ-1 המשמעות היא שהמנוע מבטיח יותר ממה",
            "> שהשוק נותן — כלומר הפוזיציות גדולות מדי (Kelly) והסף אופטימי.",
        ]
        return "\n".join(lines)


def run_calibration(
    engine,
    datasets: list[tuple[Market, list[Candle]]],
    *,
    fidelity_min: int = 60,
    horizon_hours: float = 24,
    spread: float = 0.01,
) -> CalibrationResult:
    """
    מודד את הצפי של המנוע (fair − market) מול התנועה שהתממשה בפועל.
    זה המבחן הנקי: בלי PnL, בלי Kelly, בלי סטופים.
    """
    h = max(1, int(round(horizon_hours * 60 / fidelity_min)))
    buckets: dict[str, list[tuple[float, float]]] = {}

    for market, candles in datasets:
        prices = [c.price for c in candles]
        for i in range(engine.min_candles, len(prices) - h):
            sig = engine.evaluate(market, prices[: i + 1],
                                  market_price=prices[i], spread=spread,
                                  extra={"fee_rate": market.taker_fee_rate})
            if sig.direction == "FLAT":
                continue
            sign = 1.0 if sig.direction == "LONG" else -1.0
            realized = sign * (prices[i + h] - prices[i])
            predicted = sig.edge + spread          # edge = fair - market - spread
            z = abs(float(sig.features.get("z", 0.0)))
            key = (f"z {z:.1f}" if z else "כל הסיגנלים")
            buckets.setdefault(key, []).append((predicted, realized))
            buckets.setdefault("כל הסיגנלים", []).append((predicted, realized))

    rows: list[CalibrationRow] = []
    for label, vals in sorted(buckets.items()):
        if len(vals) < 5:
            continue
        pred = sum(v[0] for v in vals) / len(vals)
        real = sum(v[1] for v in vals) / len(vals)
        hit = sum(1 for v in vals if v[1] > 0) / len(vals)
        rows.append(CalibrationRow(
            label=label, n=len(vals), predicted=pred, realized=real,
            hit_rate=hit, bias_ratio=(pred / real) if abs(real) > 1e-9 else float("inf"),
        ))

    total_pred = sum(v[0] for v in buckets.get("כל הסיגנלים", []))
    total_real = sum(v[1] for v in buckets.get("כל הסיגנלים", []))
    current = getattr(engine, "mr", None)
    current_ratio = current.reversion_ratio if current else 0.0
    suggested = current_ratio
    if abs(total_pred) > 1e-9 and abs(total_real) > 1e-9:
        # אותו סולם: מכפילים את היחס ביחס בין המציאות לצפי
        suggested = max(0.0, min(1.5, current_ratio * (total_real / total_pred)))

    return CalibrationResult(
        horizon_hours=horizon_hours,
        min_z=getattr(current, "z_entry", None) if current else None,
        rows=rows,
        suggested_ratio=suggested,
        current_ratio=current_ratio,
    )


# ======================================================================
#  פילוח לפי סקטור
# ======================================================================
def run_sector_analysis(
    engine,
    datasets: list[tuple[Market, list[Candle]]],
    *,
    fidelity_min: int = 60,
    horizon_hours: float = 48,
    spread: float = 0.01,
) -> list:
    """
    מפצל את הסיגנלים לפי סקטור ומשווה: צפי, התממשות, hit.
    המטרה: להחליט אם לצמצם את היקום (פרמטר, לא קוד).
    """
    from collections import defaultdict

    from .sectors import SectorStats, classify

    h = max(1, int(round(horizon_hours * 60 / fidelity_min)))
    acc: dict[str, SectorStats] = defaultdict(lambda: SectorStats(""))
    for market, candles in datasets:
        sector = classify(market.question, market.slug)
        stats = acc[sector]
        stats.sector = sector
        prices = [c.price for c in candles]
        for i in range(engine.min_candles, len(prices) - h):
            sig = engine.evaluate(market, prices[: i + 1],
                                  market_price=prices[i], spread=spread,
                                  extra={"fee_rate": market.taker_fee_rate})
            if sig.direction == "FLAT":
                continue
            sign = 1.0 if sig.direction == "LONG" else -1.0
            realized = sign * (prices[i + h] - prices[i])
            predicted = sig.edge + spread
            stats.n += 1
            stats.predicted += predicted
            stats.realized += realized
            stats.fees += float(sig.features.get("fees", 0.0))
            stats.hits += 1 if realized > 0 else 0
    return sorted(acc.values(), key=lambda s: -s.n)


def sectors_markdown(rows: list, horizon_hours: float = 48) -> str:
    lines = [
        "# פילוח הסיגנל לפי סקטור",
        "",
        f"אופק: {horizon_hours:g} שעות · עלות סבב = ספרד 0.01 + עמלה בפועל",
        "",
        "| סקטור | סיגנלים | hit | התממש | עמלה | נטו אחרי הכל | צפי/מציאות |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in rows:
        bias = "—" if s.bias == float("inf") else f"{s.bias:.2f}×"
        lines.append(
            f"| {s.sector} | {s.n} | {s.hit_rate * 100:.0f}% | {s.mean_realized:+.4f} "
            f"| {s.mean_fee:.4f} | {s.net_of_cost:+.4f} | {bias} |"
        )
    lines += [
        "",
        "> סקטור שנטו שלו שלילי **אחרי עמלות** הוא מועמד להחרגה (`universe.exclude_sectors`),",
        "> אבל רק אם זה שורד באימות walk-forward — ראו politics כשהוחרג בטעות.",
    ]
    return "\n".join(lines)
