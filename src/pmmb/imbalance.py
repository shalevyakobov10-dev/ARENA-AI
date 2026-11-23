"""
Order-book imbalance — איסוף וניתוח.

הרעיון: המחיר (midpoint) הוא נקודה אחת. הספר מכיל יותר: יחס הנפח בין
הביקוש להיצע בכל צד. אם הביקוש עמוס בהרבה מההיצע, סביר שהמחיר יזוז למעלה
בטווח הקצר — וזה מידע שהמחיר הנוכחי עוד לא מתמחר במלואו.

אין היסטוריית books ב-API הציבורי, ולכן **אוספים אותה בעצמנו**
(`pmmb collect`, או כל ריצת paper) ואז מודדים. בלי מדידה — לא משתמשים
בזה בסיגנל. זה הסדר הנכון.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .data.store import Store

log = logging.getLogger(__name__)


@dataclass
class BucketStats:
    label: str
    n: int = 0
    sum_move: float = 0.0
    hits: int = 0
    nonzero: int = 0

    @property
    def mean_move(self) -> float:
        return self.sum_move / self.n if self.n else 0.0

    @property
    def hit_rate(self) -> float:
        """שיעור הפעמים שהמחיר עלה — מתוך הפעמים שבהם הוא זז בכלל.

        מחיר שמסומן בטיק של 0.01 לא זז בכל דקה; ספירת האפסים כ"החמצה"
        הייתה מטעה לחלוטין בטווחי זמן קצרים.
        """
        return self.hits / self.nonzero if self.nonzero else 0.0


@dataclass
class ImbalanceReport:
    snapshots: int
    pairs: int
    horizon_min: float
    levels: int
    correlation: float
    buckets: list[BucketStats] = field(default_factory=list)
    tokens: int = 0

    @property
    def is_significant(self) -> bool:
        return self.pairs >= 300 and abs(self.correlation) >= 0.05

    def to_markdown(self) -> str:
        lines = [
            "# Order-book imbalance — מדידה",
            "",
            f"snapshots: {self.snapshots:,} · זוגות מדידה: {self.pairs:,} · "
            f"שווקים: {self.tokens} · אופק: {self.horizon_min:g} דק' · "
            f"רמות: {self.levels}",
            "",
            f"**מתאם (imbalance → תנועת מחיר עתידית): {self.correlation:+.3f}**",
            "",
            "| חוסר איזון | דגימות | תנועה עתידית | זז | hit (מזזים) |",
            "|---|---|---|---|---|",
        ]
        for b in self.buckets:
            moved = f"{b.nonzero / b.n * 100:.0f}%" if b.n else "—"
            lines.append(
                f"| {b.label} | {b.n} | {b.mean_move:+.5f} | {moved} "
                f"| {b.hit_rate * 100:.0f}% |"
            )
        lines.append("")
        if self.pairs < 300:
            lines += [
                "> ⚠️ פחות מ-300 זוגות מדידה — זה עדיין לא מדגם. "
                "הרץ `pmmb collect` לאורך שעות לפני הסקה.",
            ]
        elif abs(self.correlation) < 0.05:
            lines += ["> מתאם זניח — ה-imbalance לא נותן אות. לא מוסיפים לסיגנל."]
        else:
            lines += [
                "> יש אות. הצעד הבא: להזין את ה-imbalance כפיצ'ר בסיגנל "
                "ולאמת ב-walk-forward (לא רק על הבקטסט).",
            ]
        return "\n".join(lines)


def analyze_imbalance(
    store: Store,
    *,
    horizon_min: float = 60.0,
    levels: int = 5,
    tolerance_min: float = 20.0,
    buckets: tuple[float, ...] = (-0.6, -0.2, 0.2, 0.6),
) -> ImbalanceReport:
    """
    עבור כל snapshot של ספר: מוצא את ה-snapshot הבא של אותו טוקן אחרי
    `horizon_min` דקות (עד `tolerance_min` גרייס), ומודד את תנועת ה-mid.
    """
    rows = store.get_books()
    if not rows:
        return ImbalanceReport(0, 0, horizon_min, levels, 0.0, [], 0)

    horizon = horizon_min * 60
    tol = tolerance_min * 60

    by_token: dict[str, list] = {}
    for r in rows:
        if r["mid"] is None or r["imbalance"] is None:
            continue
        by_token.setdefault(r["token_id"], []).append(r)

    xs: list[float] = []
    ys: list[float] = []
    edges = list(buckets)
    stats = []
    labels = []
    for i in range(len(edges) + 1):
        if i == 0:
            labels.append(f"< {edges[0]:+.1f} (היצע כבד)")
        elif i == len(edges):
            labels.append(f"> {edges[-1]:+.1f} (ביקוש כבד)")
        else:
            labels.append(f"{edges[i - 1]:+.1f} … {edges[i]:+.1f}")
    stats = [BucketStats(label) for label in labels]

    pairs = 0
    for token, snaps in by_token.items():
        snaps.sort(key=lambda r: r["ts"])
        j = 0
        for i in range(len(snaps) - 1):
            t0 = snaps[i]["ts"]
            target = t0 + horizon
            j = max(j, i + 1)
            while j < len(snaps) and snaps[j]["ts"] < target:
                j += 1
            if j >= len(snaps):
                break
            t1 = snaps[j]["ts"]
            if t1 - target > tol:
                continue
            move = snaps[j]["mid"] - snaps[i]["mid"]
            imb = snaps[i]["imbalance"]
            pairs += 1
            xs.append(imb)
            ys.append(move)

            idx = 0
            for k, edge in enumerate(edges):
                if imb <= edge:
                    idx = k
                    break
            else:
                idx = len(edges)
            b = stats[idx]
            b.n += 1
            b.sum_move += move
            if move != 0:
                b.nonzero += 1
                b.hits += 1 if move > 0 else 0

    corr = 0.0
    if len(xs) >= 10:
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
        vx = sum((a - mx) ** 2 for a in xs)
        vy = sum((b - my) ** 2 for b in ys)
        if vx > 0 and vy > 0:
            corr = cov / (vx * vy) ** 0.5

    return ImbalanceReport(
        snapshots=len(rows), pairs=pairs, horizon_min=horizon_min, levels=levels,
        correlation=corr, buckets=stats, tokens=len(by_token),
    )


def write_imbalance_report(rep: ImbalanceReport, out_dir: str | Path = "reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "imbalance.md"
    path.write_text(rep.to_markdown(), encoding="utf-8")
    return path
