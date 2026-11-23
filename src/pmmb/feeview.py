"""
תצוגת הכלכלה של כל סקטור: כמה עמלה, מה עלות סבב, ואיזו תנועה נדרשת
כדי לצאת ברווח. הכלי הזה עונה על השאלה "איפה בכלל כדאי לסחור".
"""
from __future__ import annotations

from dataclasses import dataclass

from .fees import CATEGORY_TAKER_RATES, SECTOR_TO_FEE_KEY, round_trip_fee_per_share

# סקטור → שיעור עמלה תקף (עם החריגים של politics/elections)
_SECTOR_RATE = {
    "geopolitics": 0.00,
    "crypto": 0.01,
    "politics": 0.01,
    "macro": 0.01,
    "culture": 0.01,
    "weather": 0.01,
    "tech": 0.05,
    "sports": 0.05,
    "finance": 0.05,
    "other": 0.05,
}


@dataclass
class FeeRow:
    sector: str
    rate: float
    edge: float
    rt_fee: float        # עמלה הלוך-חזור למניה במחיר 0.50
    breakeven: float     # תנועה נדרשת (נקודות הסתברות) עם ספרד
    net_at_edge: float   # נטו לסיגנל טיפוסי בעובי edge
    verdict: str

    def as_dict(self) -> dict:
        return {
            "sector": self.sector, "rate": self.rate, "edge": round(self.edge, 4),
            "rt_fee": round(self.rt_fee, 4),
            "breakeven": round(self.breakeven, 4), "net_at_edge": round(self.net_at_edge, 4),
            "verdict": self.verdict,
        }


def fee_table(*, spread: float = 0.01, edge: float = 0.025, price: float = 0.50,
              measured_edges: dict[str, float] | None = None) -> list[FeeRow]:
    """
    edge = עובי הסיגנל הטיפוסי. אם יש מדידה בפועל לפי סקטור (sectors.json),
    היא גוברת על ברירת המחדל — עדיף מדד מהערכה.
    """
    measured_edges = measured_edges or {}
    rows = []
    for sector, rate in sorted(_SECTOR_RATE.items(), key=lambda kv: kv[1]):
        rt = round_trip_fee_per_share(price, rate)
        be = spread + rt
        e = float(measured_edges.get(sector, edge))
        net = e - be
        if net <= 0:
            verdict = "❌ לא משתלם"
        elif net < 0.005:
            verdict = "⚠️ שולי"
        else:
            verdict = "✅ משתלם"
        rows.append(FeeRow(sector, rate, e, rt, be, net, verdict))
    return rows


def fee_markdown(rows: list[FeeRow], *, spread: float, edge: float, price: float) -> str:
    lines = [
        "# כלכלת העמלות לפי סקטור",
        "",
        f"מחיר יחוס {price:.2f} · ספרד {spread:.3f} · עובי סיגנל: מדוד לפי סקטור או {edge:.3f} כברירת מחדל",
        "",
        "הנוסחה הרשמית: `fee = C × rate × p × (1 − p)`. **מייקרים פטורים לגמרי.**",
        "",
        "| סקטור | עמלה | עובי | עלות סבב | תנועה נדרשת | נטו לסיגנל | פסק דין |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r.sector} | {r.rate:.1%} | {r.edge:.4f} | {r.rt_fee:.4f} "
            f"| {r.breakeven:.4f} | {r.net_at_edge:+.4f} | {r.verdict} |"
        )
    lines += [
        "",
        "## מה זה אומר בפועל",
        "",
        f"- **geopolitics פטור מעמלה** — כל נקודת הסתברות שנגרפה נשארת אצלנו.",
        f"- בסקטורים של 5% (ספורט, בחירות, טק) העמלה בשיאה במרכז הטווח:",
        f"  {round_trip_fee_per_share(0.50, 0.05):.4f} הלוך-חזור — כלומר סיגנל של 2.5 סנט",
        f"  בקושי מכסה את עצמו, ולכן הסיגנל **חייב** להיות עבה יותר כדי שניכנס.",
        "- במחירים קיצוניים (0.90+) העמלה זניחה, ולכן שווקים בקצוות סובלים פחות.",
        "",
        "> המערכת מתמחרת את זה בתוך `edge` (friction = ספרד + עמלה), כך שסיגנל",
        "> שלא מכסה את העמלה נפסל אוטומטית ואינו הופך לעסקה.",
    ]
    return "\n".join(lines)


def write_fee_report(path, rows, **kw):
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(fee_markdown(rows, **kw), encoding="utf-8")
    return p
