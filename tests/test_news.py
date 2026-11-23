"""בדיקות למודול החדשות החיות ומגן קטליזטור ('סכין נופלת') — אפס רשת."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from pmmb.data.clob import Book, Candle
from pmmb.data.news import (
    NewsArticle,
    extract_keywords,
    match_market_news,
    parse_rss,
    score_headline,
)
from pmmb.data.store import Store
from pmmb.engine import Engine
from pmmb.models import Market


_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Breaking: Pedro Sanchez announces resignation ahead of confidence vote - Reuters</title>
      <link>https://example.com/a1</link>
      <pubDate>Sun, 22 Nov 2026 12:00:00 GMT</pubDate>
      <source>Reuters</source>
    </item>
    <item>
      <title>Madrid weather stays sunny this week - Local News</title>
      <link>https://example.com/a2</link>
      <pubDate>Sun, 22 Nov 2026 11:00:00 GMT</pubDate>
      <source>Local News</source>
    </item>
  </channel>
</rss>"""


def test_parse_rss_and_scoring():
    arts = parse_rss(_SAMPLE_RSS, query="Spain", category="politics")
    assert len(arts) == 2
    assert arts[0].source == "Reuters"
    assert arts[0].impact >= 0.65
    assert arts[0].sentiment < 0
    sent2, imp2 = score_headline("Candidate wins election after official confirmation")
    assert sent2 > 0 and imp2 >= 0.65


def test_extract_keywords_and_match_catalyst():
    kws = extract_keywords("Will Pedro Sanchez be the next Prime Minister of Spain?")
    assert "Pedro" in kws and "Sanchez" in kws and "Spain" in kws
    now = int(time.time())
    arts = [
        NewsArticle(id="1", ts=now - 600, title="Pedro Sanchez announces resignation in Spain", impact=0.80, sentiment=-0.7),
        NewsArticle(id="2", ts=now - 18000, title="Pedro Sanchez campaign rally", impact=0.30, sentiment=0.3),
    ]
    m = match_market_news(
        "Will Pedro Sanchez be the next Prime Minister of Spain?",
        arts, now_ts=now, window_hours=4.0, min_articles=2, impact_threshold=0.65,
    )
    assert m.catalyst_detected is True
    assert m.article_count == 1
    assert "resignation" in m.latest_title


def test_engine_news_catalyst_blocks_falling_knife(tmp_path, cfg):
    now = int(time.time())
    cfg.signal.engine = "meanrev"
    cfg.signal.meanrev.lookback_candles = 12
    cfg.signal.meanrev.z_entry = 1.5
    cfg.signal.meanrev.reversion_ratio = 0.7
    cfg.signal.min_score = 0.4
    cfg.signal.min_edge = 0.005
    cfg.universe.min_entry_hours_to_resolution = 1.0
    cfg.news.enabled = True
    cfg.news.block_on_catalyst = True
    cfg.news.spike_window_hours = 4.0
    cfg.news.spike_impact_threshold = 0.65

    import json as _json

    raw_mkt = {
        "conditionId": "0xnews1",
        "question": "Will Pedro Sanchez win the next election in Spain?",
        "slug": "sanchez-spain",
        "clobTokenIds": _json.dumps(["tok-news-yes", "tok-news-no"]),
        "outcomes": _json.dumps(["Yes", "No"]),
        "outcomePrices": _json.dumps(["0.35", "0.65"]),
        "bestBid": 0.355,
        "bestAsk": 0.365,
        "endDate": (datetime.now(tz=timezone.utc) + timedelta(days=10)).isoformat().replace("+00:00", "Z"),
        "volume24hr": "80000",
        "liquidityNum": "25000",
        "orderPriceMinTickSize": "0.01",
        "orderMinSize": "5",
        "enableOrderBook": True,
        "acceptingOrders": True,
        "closed": False,
        "archived": False,
        "negRisk": False,
        "events": [],
    }
    # סדרת מחירים עם תנודה מתונה סביב 0.55 ואז צניחה מאוזנת ל-0.46 (z ≈ -2.6, בתוך תחום MeanRev)
    import math as _math
    prices = [0.55 + 0.014 * _math.sin(i * 0.9) for i in range(44)] + [0.51, 0.48, 0.46]
    candles = [Candle(ts=now - (len(prices) - i) * 3600, price=round(p, 4)) for i, p in enumerate(prices)]
    book = Book(
        token_id="tok-news-yes", best_bid=0.455, best_ask=0.465,
        bid_size=300, ask_size=300, bids=[(0.455, 300)], asks=[(0.465, 300)],
    )

    class _Gamma:
        def fetch_markets(self, **_kw):
            return [raw_mkt]

    class _Clob:
        def get_book(self, tid):
            return book

        def get_history(self, tid, **_kw):
            return candles

        def estimate_fill(self, bk, side, notional, **_kw):
            return 0.465, notional / 0.465

    class _NewsStub:
        def fetch_live(self, *_a, **_kw):
            return [NewsArticle(
                id="brk1", ts=now - 300,
                title="Breaking: Pedro Sanchez resigns as Spain crisis deepens",
                source="Reuters", category="politics", sentiment=-0.9, impact=0.85,
            )]

    # 1. עם ידיעת חדשות שוברת — הכניסה נחסמת ("חדשות: תזוזה מונעת ידיעה")
    cfg.data.db_path = str(tmp_path / "blocked.db")
    eng1 = Engine(cfg, gamma=_Gamma(), clob=_Clob(), news_client=_NewsStub())
    st1 = eng1.run_once()
    eng1.close()
    assert st1.entries == 0
    assert st1.skipped.get("חדשות: תזוזה מונעת ידיעה", 0) == 1

    # 2. בלי חדשות חריגות — אותו אות בדיוק נכנס לעסקה
    class _QuietNews:
        def fetch_live(self, *_a, **_kw):
            return []

    cfg.data.db_path = str(tmp_path / "allowed.db")
    eng2 = Engine(cfg, gamma=_Gamma(), clob=_Clob(), news_client=_QuietNews())
    st2 = eng2.run_once()
    eng2.close()
    assert st2.entries == 1


def test_news_rejects_generic_single_word_false_positives_and_catches_corporate_catalysts():
    now = int(time.time())
    # מילים גנריות ("announces", "reported") לא משדכות כתבות לא קשורות לשווקים
    false_arts = [
        NewsArticle(id="f1", ts=now - 300, title="India announces a $1.6 billion aid package for flood recovery", impact=0.56, sentiment=1.0),
        NewsArticle(id="f2", ts=now - 300, title="Sinner to undergo knee surgery, Italian media reported", impact=0.20, sentiment=-0.5),
    ]
    m_iran = match_market_news("US announces end of Iranian blockade by December?", false_arts, now_ts=now, min_articles=1, impact_threshold=0.0)
    m_huang = match_market_news("Will 3 Jensen Huang affairs be reported before 2027?", false_arts, now_ts=now, min_articles=1, impact_threshold=0.0)
    assert m_iran.article_count == 0
    assert m_huang.article_count == 0

    # אירועי אמת פיננסיים/משפטיים מזוהים כקטליזטורים בעלי impact גבוה
    s1, i1 = score_headline("Nvidia reinstates former CEO Jensen Huang despite China espionage scandal")
    s2, i2 = score_headline("Exclusive | SEC Is Probing Nvidia Amid CEO Departure")
    assert i1 >= 0.65 and s1 < 0
    assert i2 >= 0.45 and s2 < 0

