#!/usr/bin/env python3
"""
מחקר: הטיית פייבוריט/לונגשוט על שווקים שהסתיימו.

השאלה: כששוק מתומחר ב-0.95, האם הוא מסתיים YES ב-95% מהמקרים —
או ביותר (פייבוריטים זולים מדי) / בפחות (לונגשוטים יקרים מדי)?

אם פייבוריטים מסתיימים ב-96%+, קניית פייבוריטים היא edge מבני
שעובד בכל קטגוריה — לא תלוי בסיגנל ולא במומנטום.

    python scripts/research_bias.py --markets 300 --horizon-hours 24
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics as st
from datetime import datetime

from pmmb.data.clob import ClobClient
from pmmb.data.gamma import GammaClient
from pmmb.data.http import HttpClient


def fetch_resolved(gamma: GammaClient, target: int, min_volume: float) -> list[dict]:
    out: list[dict] = []
    offset = 0
    while len(out) < target:
        page = gamma.http.get("/markets", params={
            "limit": 100, "offset": offset, "closed": "true",
            "order": "volumeNum", "ascending": "false",
        })
        if not page:
            break
        for m in page:
            try:
                vol = float(m.get("volumeNum") or m.get("volume") or 0)
            except (TypeError, ValueError):
                vol = 0.0
            if vol >= min_volume and m.get("clobTokenIds") and m.get("endDate"):
                prices = json.loads(m.get("outcomePrices") or "[]")
                if prices and prices[0] in ("0", "1", "0.0", "1.0"):
                    out.append(m)
        offset += 100
        if offset > 2000:
            break
    return out[:target]


def price_before(clob: ClobClient, token: str, end_ts: int, hours: float) -> float | None:
    start = end_ts - int(hours * 3600) - 3 * 86400
    try:
        h = clob.http.get("/prices-history", params={
            "market": token, "startTs": start, "endTs": end_ts, "fidelity": 60,
        }).get("history", [])
    except ConnectionError:
        return None
    if not h:
        return None
    cutoff = end_ts - int(hours * 3600)
    before = [p for p in h if p["t"] <= cutoff]
    if not before:
        return None
    return float(before[-1]["p"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", type=int, default=300)
    ap.add_argument("--min-volume", type=float, default=2000)
    ap.add_argument("--horizon-hours", type=float, default=24)
    ap.add_argument("--bin", type=float, default=0.05)
    args = ap.parse_args()

    clob = ClobClient(HttpClient("https://clob.polymarket.com", rate_limit_rps=12))
    gamma = GammaClient(HttpClient("https://gamma-api.polymarket.com", rate_limit_rps=12))

    print(f"שולף עד {args.markets} שווקים סגורים (volume ≥ {args.min_volume:,.0f})...")
    markets = fetch_resolved(gamma, args.markets, args.min_volume)
    print(f"נמצאו {len(markets)} מועמדים. שולף מחיר {args.horizon_hours:g}ש' לפני הסגירה...\n")

    bins: dict[float, list[tuple[float, int]]] = collections.defaultdict(list)
    used = 0
    for i, m in enumerate(markets, 1):
        try:
            end = datetime.fromisoformat(str(m["endDate"]).replace("Z", "+00:00"))
            end_ts = int(end.timestamp())
            tokens = json.loads(m["clobTokenIds"])
            outcomes = [str(o).strip().lower() for o in json.loads(m["outcomes"])]
            prices = json.loads(m["outcomePrices"])
            # לא כל השווקים מסודרים [Yes, No] — חייבים למפות לפי התווית
            yes_idx = outcomes.index("yes") if "yes" in outcomes else 0
            token = tokens[yes_idx]
            resolved_yes = 1 if prices[yes_idx] in ("1", "1.0") else 0
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        price = price_before(clob, token, end_ts, args.horizon_hours)
        if price is None or not (0.0 < price < 1.0):
            continue
        bucket = round(price / args.bin) * args.bin
        bins[round(bucket, 2)].append((price, resolved_yes))
        used += 1
        if i % 50 == 0:
            print(f"  ...{i}/{len(markets)} (נכללו {used})", end="\r", flush=True)

    print(f"\nנכללו {used} שווקים עם מחיר ותוצאה.\n")
    print(f"{'מחיר':>7s} {'n':>4s} {'מחיר ממוצע':>10s} {'YES%':>6s} {'הפרש':>7s} "
          f"{'EV קניית YES':>13s} {'EV קניית NO':>12s}")
    print("-" * 72)
    tot = {"yes": [], "no": []}
    for b in sorted(bins):
        rows = bins[b]
        if len(rows) < 5:
            continue
        yes_rate = sum(r[1] for r in rows) / len(rows)
        ev_yes = sum((1 - r[0]) if r[1] else -r[0] for r in rows) / len(rows)
        ev_no = sum(-(1 - r[0]) if r[1] else r[0] for r in rows) / len(rows)
        tot["yes"].extend([(1 - r[0]) if r[1] else -r[0] for r in rows])
        tot["no"].extend([-(1 - r[0]) if r[1] else r[0] for r in rows])
        avg = st.mean(r[0] for r in rows)
        print(f"{b:7.2f} {len(rows):4d} {avg:10.3f} {yes_rate * 100:5.0f}% "
              f"{yes_rate * 100 - avg * 100:+6.1f} {ev_yes:+13.4f} {ev_no:+12.4f}")
    if tot["yes"]:
        print("-" * 72)
        print(f"EV כולל: קניית YES {st.mean(tot['yes']):+.4f} · "
              f"קניית NO {st.mean(tot['no']):+.4f}")
        print("\n(עלות סבב ~0.01 — EV חיובי חייב לעלות על זה)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
