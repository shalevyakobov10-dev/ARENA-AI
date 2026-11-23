"""
פיד חדשות שווקים חיות וזיהוי קטליזטורים (News & Catalyst Guard).

משתמש במקורות פתוחים בזמן אמת (Google News RSS) + התאמה דטרמיניסטית לשאלות השוק.
המטרה הכמותית: להבדיל בין צניחת נזילות מקרית (שמתאימה ל-Mean Reversion)
לבין תנועה המונעת מידיעה חדשותית שוברת ("סכין נופלת" שאסור לקנות).
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import quote_plus

import httpx

log = logging.getLogger(__name__)

_DEFAULT_FEEDS: tuple[tuple[str, str, str], ...] = (
    ("macro", "Federal Reserve inflation interest rates", "Federal Reserve OR inflation OR tariffs OR GDP"),
    ("politics", "US & World Elections Politics", "election OR prime minister OR president OR senate OR parliament"),
    ("geopolitics", "Geopolitics & Diplomacy", "ceasefire OR sanctions OR NATO OR Taiwan OR Ukraine"),
    ("markets", "Polymarket & Markets", "Polymarket OR IPO OR antitrust OR SEC"),
    ("sports", "Sports Injuries & Breaking", "NBA OR NFL OR UFC injured OR suspended OR trade"),
)

# 19 רשתות חדשות מוסדיות מכל העולם — נמשכות במקביל (~0.5 שנ'), ללא מגבלות 429
_WIRE_FEEDS: tuple[tuple[str, str, str], ...] = (
    ("geopolitics", "BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("macro", "BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("tech", "BBC Tech", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("geopolitics", "Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("geopolitics", "DW World", "https://rss.dw.com/xml/rss-en-all"),
    ("geopolitics", "France 24", "https://www.france24.com/en/rss"),
    ("markets", "CNBC Top", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
    ("geopolitics", "CNBC World", "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ("politics", "NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ("markets", "MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    ("crypto", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("geopolitics", "NYT World", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
    ("macro", "NYT Business", "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml"),
    ("geopolitics", "Guardian World", "https://www.theguardian.com/world/rss"),
    ("sports", "Sky Sports", "https://www.skysports.com/rss/12040"),
    ("geopolitics", "SCMP Asia", "https://www.scmp.com/rss/91/feed"),
    ("geopolitics", "CNA Asia", "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml"),
    ("macro", "Fed Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("politics", "Politico", "https://rss.politico.com/politics-news.xml"),
)

_STOP_WORDS = frozenset({
    "will", "the", "a", "an", "in", "on", "at", "to", "for", "of", "and", "or", "by", "be",
    "is", "are", "was", "were", "has", "have", "had", "does", "do", "did", "with", "from",
    "this", "that", "these", "those", "next", "most", "more", "than", "least", "win", "wins",
    "won", "lose", "seats", "election", "market", "before", "after", "during", "end", "year",
    "january", "february", "march", "april", "may", "june", "july", "august", "september",
    "october", "november", "december", "2024", "2025", "2026", "2027", "vs", "over", "under",
    "reach", "above", "below", "between", "party", "become", "remain", "another", "other",
    "any", "all", "new", "first", "second", "third", "high", "low", "how", "many", "much",
    "what", "which", "who", "when", "where", "yes", "no", "not", "into", "out", "up", "down",
    "prime", "minister", "president", "next", "governor", "mayor",
    "elections", "government", "local", "head", "political", "parties", "country", "countries",
    "national", "global", "world", "company", "companies", "shares", "price", "prices", "close",
    "level", "target", "series", "match", "game", "season", "round", "total", "spread",
    "points", "quarter", "month", "week", "today", "tomorrow", "general", "state", "city",
    "rate", "rates", "increase", "decrease", "change", "continue", "continues", "through",
    "reported", "report", "reports", "announces", "announced", "announce", "closure",
    "listed", "leader", "leaders", "affairs", "leaving", "leave", "finish", "finished",
    "meeting", "diplomatic", "effective", "publicly", "testify", "searched", "person",
    "people", "million", "billion", "percent", "administration", "official", "officials",
    "stocks", "sources", "terms", "becomes", "calling", "ordered", "underway",
})

_HIGH_IMPACT = frozenset({
    "breaking", "official", "announced", "announces", "drops out", "resigns", "resigned",
    "wins", "won", "elected", "concedes", "ceasefire", "sanctions", "rate cut", "rate hike",
    "emergency", "indicted", "arrested", "injured", "injury", "ruled out", "suspended",
    "cancelled", "canceled", "bankrupt", "bankruptcy", "acquired", "merger", "ipo",
    "approved", "vetoed", "rejected", "confirmed", "surges", "plunges", "crashes", "collapses",
    "assassination", "coup", "impeached", "default", "halt", "halted", "verdict", "guilty",
    "probe", "probing", "investigation", "espionage", "scandal", "reinstates", "reinstated",
    "returns as ceo", "step down", "steps down", "ousted", "fired", "sacked", "subpoena",
    "testify", "testifies", "indictment", "blockade", "airspace", "shutdown", "soars",
    "jumps", "tariff", "tariffs",
})

_POS_WORDS = frozenset({
    "wins", "won", "leads", "leading", "approved", "passes", "passed", "confirmed",
    "surges", "rises", "rally", "deal", "ceasefire", "agreement", "recovery", "beats",
    "nominated", "endorsed", "boost", "growth", "stronger", "victory",
    "reinstates", "reinstated", "returns", "soars", "jumps", "reopens", "lifted",
})

_NEG_WORDS = frozenset({
    "loses", "lost", "drops", "resigns", "resigned", "resignation", "withdraw", "withdraws",
    "injured", "injury", "out", "rejected", "vetoed", "crashes", "plunges", "collapses",
    "indicted", "arrested", "fails", "failed", "crisis", "war", "escalation", "sanctions",
    "bankrupt", "default", "scandal", "probe", "probing", "investigation", "espionage",
    "ousted", "fired", "sacked", "subpoena", "indictment", "shutdown", "blockade",
    "delay", "delayed", "cancelled", "canceled", "slumps", "falls", "guilty", "warns", "downgrade",
})


@dataclass
class NewsArticle:
    id: str
    ts: int
    title: str
    source: str = ""
    url: str = ""
    query: str = ""
    category: str = "macro"
    sentiment: float = 0.0
    impact: float = 0.0
    matched_tokens: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "query": self.query,
            "category": self.category,
            "sentiment": round(self.sentiment, 2),
            "impact": round(self.impact, 2),
            "matched_tokens": self.matched_tokens,
        }


@dataclass
class NewsMatch:
    article_count: int = 0
    max_impact: float = 0.0
    avg_sentiment: float = 0.0
    catalyst_detected: bool = False
    latest_title: str = ""
    matched_titles: list[str] | None = None


def score_headline(title: str) -> tuple[float, float]:
    """מחזיר (sentiment [-1..+1], impact [0..1]) באופן דטרמיניסטי ומהיר."""
    low = title.lower()
    hi_hits = sum(1 for k in _HIGH_IMPACT if k in low)
    pos_hits = sum(1 for k in _POS_WORDS if re.search(rf"\b{re.escape(k)}\b", low))
    neg_hits = sum(1 for k in _NEG_WORDS if re.search(rf"\b{re.escape(k)}\b", low))

    impact = min(1.0, 0.20 + hi_hits * 0.28 + (pos_hits + neg_hits) * 0.08)
    total_pol = pos_hits + neg_hits
    sentiment = (pos_hits - neg_hits) / total_pol if total_pol > 0 else 0.0
    return round(sentiment, 3), round(impact, 3)


def extract_keywords(question: str, max_words: int = 4) -> list[str]:
    """מחלץ מילות מפתח ייחודיות משאלת שוק לצורך התאמת חדשות ושאילתת RSS."""
    raw_words = re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", question or "")
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for w in raw_words:
        lw = w.lower()
        if lw in _STOP_WORDS or lw in seen:
            continue
        seen.add(lw)
        # עדיפות לשמות פרטיים / ראשי תיבות / מילים ארוכות
        bonus = (3 if w[0].isupper() else 0) + (2 if len(w) >= 6 else 0)
        scored.append((bonus, w))
    scored.sort(key=lambda x: (-x[0], -len(x[1])))
    return [w for _, w in scored[:max_words]]


def parse_rss(xml_text: str, *, query: str = "", category: str = "macro",
              now_ts: int | None = None, limit: int = 12) -> list[NewsArticle]:
    """מפרסר פיד Google News RSS (או RSS 2.0 תקני) בלי תלויות חיצוניות."""
    now_ts = int(now_ts or time.time())
    articles: list[NewsArticle] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    for item in root.findall(".//item"):
        raw_title = (item.findtext("title") or "").strip()
        if not raw_title:
            continue
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None and source_el.text else ""
        title = raw_title
        if " - " in raw_title:
            parts = raw_title.rsplit(" - ", 1)
            title = parts[0].strip()
            if not source:
                source = parts[1].strip()

        pub_txt = (item.findtext("pubDate") or "").strip()
        ts = now_ts
        if pub_txt:
            try:
                ts = int(parsedate_to_datetime(pub_txt).timestamp())
            except Exception:
                ts = now_ts

        link = (item.findtext("link") or "").strip()
        sentiment, impact = score_headline(title)
        aid = hashlib.sha1(f"{title.lower()}|{source.lower()}".encode("utf-8")).hexdigest()[:20]
        articles.append(NewsArticle(
            id=aid, ts=ts, title=title[:220], source=source[:60], url=link[:300],
            query=query[:80], category=category, sentiment=sentiment, impact=impact,
        ))
        if len(articles) >= limit:
            break
    return articles


def match_market_news(
    question: str,
    articles: Iterable[NewsArticle | dict],
    *,
    now_ts: int | None = None,
    window_hours: float = 4.0,
    min_articles: int = 2,
    impact_threshold: float = 0.65,
) -> NewsMatch:
    """מתאים כתבות טריות לשוק ומכריע אם קיים קטליזטור חדשותי שובר."""
    raw_kws = extract_keywords(question, max_words=5)
    if not raw_kws:
        return NewsMatch()
    kws = [k.lower() for k in raw_kws]
    proper_kws = {k.lower() for k in raw_kws if k[0].isupper() or k.isupper()}
    now_ts = int(now_ts or time.time())
    cutoff = int(now_ts - window_hours * 3600)
    min_hits = 1 if len(kws) == 1 else 2
    kw_pats = [(k, re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)) for k in kws]

    matched: list[tuple[int, float, float, str]] = []
    for art in articles:
        if isinstance(art, dict):
            ts = int(art.get("ts") or 0)
            title = str(art.get("title") or "")
            impact = float(art.get("impact") or 0.0)
            sent = float(art.get("sentiment") or 0.0)
        else:
            ts = int(art.ts)
            title = art.title
            impact = float(art.impact)
            sent = float(art.sentiment)
        if ts < cutoff:
            continue
        matched_kws = [k for k, pat in kw_pats if pat.search(title)]
        hits = len(matched_kws)
        # מילה יחידה תקפה רק אם היא שם ישות ייחודי (אות גדולה בשאלה) באורך >= 7 או שיש רק מילת מפתח אחת
        single_proper = hits == 1 and any(len(k) >= 7 and k in proper_kws for k in matched_kws)
        if hits >= min_hits or single_proper:
            matched.append((ts, impact, sent, title))

    if not matched:
        return NewsMatch()
    matched.sort(key=lambda x: -x[0])
    max_imp = max(m[1] for m in matched)
    avg_sent = sum(m[2] for m in matched) / len(matched)
    catalyst = len(matched) >= min_articles or max_imp >= impact_threshold
    return NewsMatch(
        article_count=len(matched),
        max_impact=round(max_imp, 3),
        avg_sentiment=round(avg_sent, 3),
        catalyst_detected=catalyst,
        latest_title=matched[0][3],
        matched_titles=[m[3] for m in matched[:5]],
    )


class NewsClient:
    """קליינט RSS קל-משקל וחסין לתקלות רשת."""

    RSS_BASE = "https://news.google.com/rss/search"

    def __init__(self, timeout: float = 4.5, http_client: httpx.Client | None = None) -> None:
        self.timeout = timeout
        self._client = http_client

    def _get(self, url: str) -> tuple[int, str | None]:
        try:
            if self._client is not None:
                r = self._client.get(url, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout, follow_redirects=True,
                                  headers={"User-Agent": "pmmb/1.0"}) as c:
                    r = c.get(url)
            if r.status_code == 200:
                return 200, r.text
            return int(r.status_code), None
        except Exception as exc:
            log.debug("קריאת חדשות נכשלה (%s): %s", url[:70], exc)
        return 0, None

    def fetch_query(self, query: str, *, category: str = "macro", limit: int = 8) -> list[NewsArticle]:
        url = f"{self.RSS_BASE}?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
        code, xml = self._get(url)
        if code == 429:
            raise RuntimeError("rate_limited_429")
        if not xml:
            return []
        return parse_rss(xml, query=query, category=category, limit=limit)

    def fetch_live(self, markets: Iterable = (), *, max_market_queries: int = 8) -> list[NewsArticle]:
        seen: dict[str, NewsArticle] = {}

        # 1. משיכה מקבילית של 14 רשתות החדשות המוסדיות מכל העולם (~0.5 שנ')
        def _fetch_wire(item: tuple[str, str, str]) -> list[NewsArticle]:
            cat, src_name, rss_url = item
            _code, xml = self._get(rss_url)
            if not xml:
                return []
            arts = parse_rss(xml, query=src_name, category=cat, limit=10)
            for art in arts:
                if not art.source:
                    art.source = src_name
            return arts

        if self._client is None:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for arts in pool.map(_fetch_wire, _WIRE_FEEDS):
                    for art in arts:
                        seen[art.id] = art
        else:
            for item in _WIRE_FEEDS:
                for art in _fetch_wire(item):
                    seen[art.id] = art

        # 2. שאילתות Google News עם בקרת קצב מנומסת (עוצר מיד ב-429 כדי לא להיחסם)
        gnews_blocked = False
        for cat, _label, q in _DEFAULT_FEEDS:
            if gnews_blocked:
                break
            try:
                for art in self.fetch_query(q, category=cat, limit=8):
                    seen[art.id] = art
                if self._client is None:
                    time.sleep(0.25)
            except RuntimeError:
                gnews_blocked = True
                log.debug("Google News החזיר 429 — ממשיך עם רשת הפידים הגלובלית")

        # 3. שאילתות ממוקדות לשווקים פתוחים/פעילים
        asked: set[str] = set()
        for mk in markets:
            if gnews_blocked or len(asked) >= max_market_queries:
                break
            q_text = getattr(mk, "question", "") or ""
            kws = extract_keywords(q_text, max_words=3)
            if len(kws) < 2:
                continue
            q = " ".join(kws)
            if q.lower() in asked:
                continue
            asked.add(q.lower())
            cat = getattr(mk, "sector", "") or "market"
            tid = (getattr(mk, "yes_token_id", "") or "")[:12]
            try:
                for art in self.fetch_query(q, category=cat, limit=5):
                    if tid and q_text:
                        chk = match_market_news(q_text, [art], window_hours=168, min_articles=1, impact_threshold=0.0)
                        if chk.article_count > 0 and tid not in art.matched_tokens:
                            art.matched_tokens = f"{art.matched_tokens},{tid}".strip(",")
                    seen[art.id] = art
                if self._client is None:
                    time.sleep(0.25)
            except RuntimeError:
                gnews_blocked = True
                break

        return sorted(seen.values(), key=lambda a: -a.ts)


def infer_region(source: str, category: str, title: str) -> str:
    """משייך ידיעה לאזור גיאוגרפי / שוק דומיננטי לתצוגת רדאר בינלאומי."""
    blob = f"{source} {title}".lower()
    if any(k in blob for k in ("taiwan", "china", "beijing", "scmp", "cna asia", "japan", "korea", "taipei", "hong kong", "singapore", "asia")):
        return "אסיה"
    if any(k in blob for k in ("israel", "iran", "gaza", "lebanon", "syria", "al jazeera", "middle east", "saudi", "qatar", "netanyahu", "tehran")):
        return "מזרח תיכון"
    if any(k in blob for k in ("bbc", "france 24", "dw", "guardian", "ukraine", "russia", "europe", "eu ", "nato", "spain", "germany", "uk ", "london", "paris")):
        return "אירופה"
    if category == "sports" or any(k in blob for k in ("nba", "nfl", "ufc", "sky sports", "premier league", "arsenal", "broncos", "thunder")):
        return "ספורט"
    if category == "crypto" or any(k in blob for k in ("coindesk", "bitcoin", "ethereum", "crypto", "solana")):
        return "קריפטו"
    if any(k in blob for k in ("fed", "federal reserve", "politico", "npr", "cnbc", "nyt", "marketwatch", "wall street", "congress", "trump", "senate", "us ")):
        return "אמריקה ושווקים"
    return "גלובלי"


def compute_global_pulse(articles: Iterable[NewsArticle | dict]) -> dict:
    """מחשב מדד מצב חדשות גלובלי בזמן אמת (סנטימנט, צפיפות קטליזטורים, סקטורים, אזורים ומקורות)."""
    items = list(articles)
    if not items:
        return {
            "total": 0, "avg_sentiment": 0.0, "catalysts": 0,
            "regime": "שקט", "sources": 0, "by_category": {}, "by_region": {},
        }
    sents: list[float] = []
    catalysts = 0
    sources: set[str] = set()
    by_cat: dict[str, int] = {}
    by_reg: dict[str, int] = {}
    for a in items:
        s = float(a.get("sentiment") or 0.0) if isinstance(a, dict) else float(a.sentiment)
        imp = float(a.get("impact") or 0.0) if isinstance(a, dict) else float(a.impact)
        src = str(a.get("source") or "") if isinstance(a, dict) else str(a.source)
        cat = str(a.get("category") or "world") if isinstance(a, dict) else str(a.category)
        ttl = str(a.get("title") or "") if isinstance(a, dict) else str(a.title)
        reg = infer_region(src, cat, ttl)
        sents.append(s)
        if imp >= 0.45:
            catalysts += 1
        if src:
            sources.add(src)
        by_cat[cat] = by_cat.get(cat, 0) + 1
        by_reg[reg] = by_reg.get(reg, 0) + 1

    avg_s = sum(sents) / len(sents)
    cat_ratio = catalysts / len(items)
    if cat_ratio >= 0.30 and avg_s <= -0.15:
        regime = "סערה שלילית"
    elif cat_ratio >= 0.25:
        regime = "תנודתי (חדשות חריגות)"
    elif avg_s >= 0.12:
        regime = "חיובי (Risk-On)"
    elif avg_s <= -0.12:
        regime = "זהיר (Risk-Off)"
    else:
        regime = "מאוזן"

    return {
        "total": len(items),
        "avg_sentiment": round(avg_s, 3),
        "catalysts": catalysts,
        "regime": regime,
        "sources": len(sources),
        "by_category": dict(sorted(by_cat.items(), key=lambda kv: -kv[1])),
        "by_region": dict(sorted(by_reg.items(), key=lambda kv: -kv[1])),
    }


def refresh_news_to_store(
    store,
    *,
    markets: Iterable = (),
    news_client: NewsClient | None = None,
    max_market_queries: int = 8,
) -> list[NewsArticle]:
    """מושך חדשות חיות, משדך אותן לשווקים פתוחים/מועמדים, ושומר ב-SQLite."""
    client = news_client or NewsClient()
    mkt_list = list(markets)
    articles = client.fetch_live(mkt_list, max_market_queries=max_market_queries)

    # שידוך אוטומטי גם מול כותרות שוק כלליות שלא נשאלו ישירות
    for art in articles:
        hits = []
        for mk in mkt_list:
            q_text = getattr(mk, "question", "") or ""
            tid = (getattr(mk, "yes_token_id", "") or "")[:12]
            if not tid:
                continue
            m = match_market_news(q_text, [art], window_hours=72, min_articles=1, impact_threshold=0.0)
            if m.article_count > 0:
                hits.append(tid)
        if hits:
            prev = [x for x in art.matched_tokens.split(",") if x]
            merged = list(dict.fromkeys([*prev, *hits]))
            art.matched_tokens = ",".join(merged[:6])

    if articles:
        store.upsert_news([a.as_dict() for a in articles])
    return articles
