#!/usr/bin/env python3
"""
מחקר הסיגנל — שני הניסויים שהובילו לבניית מנוע ה-meanrev, משוחזרים כאן.

    python scripts/research_signal.py            # שני הניסויים
    python scripts/research_signal.py --deciles  # רק ניסוי 1
    python scripts/research_signal.py --context  # רק ניסוי 2

ניסוי 1 — האם יש מומנטום או היפוך?
    מחלקים את הדגימות לעשירונים לפי התנועה ב-12 הנרות האחרונים,
    ומודדים את התנועה ב-24 הנרות הבאים.

ניסוי 2 — איפה ההיפוך עובד?
    לכל צניחה חריגה (z<-1.5) מודדים את חוזק המגמה הארוכה (שיפוע 72 נרות)
    ובודקים אם התיקון תלוי בהקשר.

⚠️  אזהרה מתודולוגית: הדגימות חופפות בזמן (אותה תנועה נספרת כמה פעמים)
    והשווקים מעטים. המספרים כאן הם כיוון מחקר, לא הוכחה סטטיסטית.
"""
from __future__ import annotations

import argparse
import collections
import math
import statistics as st

from pmmb.config import Config
from pmmb.data.clob import ClobClient
from pmmb.data.gamma import GammaClient, MarketUniverse
from pmmb.data.http import HttpClient
from pmmb.signals import indicators as ind


def load_series(cfg: Config, markets: int, lookback: int) -> list[list[float]]:
    clob = ClobClient(HttpClient(cfg.data.clob_base_url))
    gamma = GammaClient(HttpClient(cfg.data.gamma_base_url))
    universe = MarketUniverse(gamma, cfg.universe).scan()[:markets]
    out = []
    for mk in universe:
        candles = clob.get_history(mk.yes_token_id, fidelity_min=60,
                                   lookback_candles=lookback, use_cache=False)
        if len(candles) > 100:
            out.append([c.price for c in candles])
    return out


def experiment_deciles(series: list[list[float]], past_n=12, fwd_n=24) -> None:
    rows = []
    for p in series:
        for i in range(past_n, len(p) - fwd_n):
            past, fwd = p[i] - p[i - past_n], p[i + fwd_n] - p[i]
            if abs(past) > 1e-9:
                rows.append((past, fwd))
    n = len(rows)
    mx, my = st.mean(r[0] for r in rows), st.mean(r[1] for r in rows)
    cov = sum((a - mx) * (b - my) for a, b in rows)
    vx = sum((a - mx) ** 2 for a, _ in rows)
    vy = sum((b - my) ** 2 for _, b in rows)
    print(f"\n=== ניסוי 1: מומנטום או היפוך? ({n:,} דגימות) ===")
    print(f"corr(תנועה {past_n} נרות, תנועה {fwd_n} נרות קדימה) = {cov / math.sqrt(vx * vy):+.3f}")
    rows.sort()
    k = n // 10
    print(f"\n{'עשירון':10s} {'תנועה קודמת':>12s} {'תנועה עתידית':>13s} {'hit':>6s}")
    for d in range(10):
        chunk = rows[d * k:(d + 1) * k] if d < 9 else rows[9 * k:]
        print(f"D{d + 1:<9d} {st.mean(x[0] for x in chunk):+12.4f} "
              f"{st.mean(x[1] for x in chunk):+13.4f} "
              f"{sum(1 for x in chunk if x[1] > 0) / len(chunk) * 100:5.0f}%")


def experiment_context(series: list[list[float]], n=12, fwd_n=24, vol_win=30) -> None:
    buckets: dict[str, list[float]] = collections.defaultdict(list)
    for p in series:
        for i in range(72, len(p) - fwd_n):
            w = p[: i + 1]
            move = w[-1] - w[-1 - n]
            hist = w[:-n] if len(w) > n + vol_win else w
            vol = ind.realized_vol(hist, vol_win)
            typical = max(vol * w[-1] * math.sqrt(n), 0.002)
            z = move / typical
            if not (-6 < z < -1.5):        # רק צניחות משמעותיות, לא קריסות
                continue
            trend_norm = ind.slope(w, 72) * 72 / typical
            key = ("מגמת ירידה חזקה" if trend_norm < -3
                   else "ניטרלי" if abs(trend_norm) < 3 else "מגמת עלייה חזקה")
            buckets[key].append(p[i + fwd_n] - p[i])

    print(f"\n=== ניסוי 2: איפה צניחה מתקנת? (z<-1.5, אופק {fwd_n}) ===")
    print(f"{'הקשר':20s} {'n':>5s} {'תיקון ממוצע':>13s} {'hit':>6s} {'נטו מ-0.01':>12s}")
    for key in ("מגמת ירידה חזקה", "ניטרלי", "מגמת עלייה חזקה"):
        v = buckets.get(key) or []
        if not v:
            continue
        print(f"{key:20s} {len(v):5d} {st.mean(v):+13.4f} "
              f"{sum(1 for x in v if x > 0) / len(v) * 100:5.0f}% {st.mean(v) - 0.01:+12.4f}")
    print("\n⚠️  דגימות חופפות + מעט שווקים = כיוון, לא הוכחה. "
          "כל מסנן שייגזר מכאן חייב לעבור walk-forward.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", type=int, default=14)
    ap.add_argument("--lookback", type=int, default=1440)
    ap.add_argument("--deciles", action="store_true")
    ap.add_argument("--context", action="store_true")
    args = ap.parse_args()

    cfg = Config.load()
    series = load_series(cfg, args.markets, args.lookback)
    print(f"נטענו {len(series)} סדרות, {sum(len(s) for s in series):,} נרות שעתיים")
    if not series:
        print("אין דאטה.")
        return 1

    do_all = not (args.deciles or args.context)
    if do_all or args.deciles:
        experiment_deciles(series)
    if do_all or args.context:
        experiment_context(series)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
