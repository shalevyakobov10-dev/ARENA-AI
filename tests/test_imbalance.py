"""Book imbalance: חישוב, איסוף וניתוח."""
import pytest

from pmmb.data.clob import Book
from pmmb.data.store import Store
from pmmb.imbalance import analyze_imbalance, write_imbalance_report


def _book(bid_sizes, ask_sizes, mid=0.5):
    bids = [(round(mid - 0.01 * (i + 1), 4), s) for i, s in enumerate(bid_sizes)]
    asks = [(round(mid + 0.01 * (i + 1), 4), s) for i, s in enumerate(ask_sizes)]
    return Book(token_id="t", best_bid=bids[0][0], best_ask=asks[0][0],
                bid_size=bid_sizes[0], ask_size=ask_sizes[0], bids=bids, asks=asks)


def test_imbalance_bounds():
    assert _book([100], [100]).imbalance(1) == 0.0
    assert _book([300], [100]).imbalance(1) == pytest.approx(0.5)
    assert _book([100], [300]).imbalance(1) == pytest.approx(-0.5)


def test_imbalance_levels():
    b = _book([100, 100], [100, 100])
    b.bids[1] = (b.bids[1][0], 300)
    assert b.imbalance(1) == 0.0
    assert b.imbalance(2) > 0.1


def test_empty_book_returns_none():
    b = Book(token_id="t", best_bid=None, best_ask=None, bid_size=0, ask_size=0)
    assert b.imbalance() is None


def test_depth_sums_levels():
    b = _book([10, 20, 30], [5, 5, 5])
    assert b.depth(2) == (30, 10)
    assert b.depth(3) == (60, 15)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "imb.db")
    yield s
    s.close()


def test_no_data_message(store):
    rep = analyze_imbalance(store, horizon_min=60)
    assert rep.snapshots == 0 and rep.pairs == 0
    assert rep.correlation == 0.0


def test_analyze_detects_positive_correlation(store):
    """כשהביקוש כבד המחיר עולה בסבב הבא — המתאם חייב לצאת חיובי."""
    token = "yes-1"
    ts0 = 1_700_000_000
    step = 600
    # בונים סדרה: המחיר בכל snapshot נקבע ע"י ה-imbalance של הקודם
    mid = 0.50
    for i in range(60):
        heavy_bid = i % 2 == 0
        book = _book([500] if heavy_bid else [50], [50] if heavy_bid else [500], mid=mid)
        store.record_book(token, ts=ts0 + i * step, book=book, levels=1)
        mid = round(mid + (0.02 if heavy_bid else -0.02), 4)

    rep = analyze_imbalance(store, horizon_min=10, tolerance_min=0)
    assert rep.pairs > 20
    assert rep.correlation > 0.5
    assert rep.buckets[-1].mean_move > 0        # ביקוש כבד → תנועה חיובית
    assert "imbalance" in rep.to_markdown()


def test_report_warns_on_small_sample(store):
    book = _book([100], [100])
    store.record_book("t", ts=1_700_000_000, book=book)
    store.record_book("t", ts=1_700_000_600, book=book)
    rep = analyze_imbalance(store, horizon_min=10, tolerance_min=0)
    assert "⚠️" in rep.to_markdown()
    assert not rep.is_significant


def test_write_report(store, tmp_path):
    rep = analyze_imbalance(store, horizon_min=10)
    path = write_imbalance_report(rep, tmp_path)
    assert path.name == "imbalance.md"
