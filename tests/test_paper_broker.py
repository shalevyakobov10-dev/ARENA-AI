from pmmb.data.clob import Book
from pmmb.execution.paper import PaperBroker
from pmmb.models import Order


class _FakeClob:
    def __init__(self, book):
        self._book = book

    def get_book(self, token_id):
        return self._book

    def estimate_fill(self, book, side, notional, max_impact_pct=0.02, allow_partial=False):
        from pmmb.data.clob import ClobClient

        return ClobClient.estimate_fill(None, book, side, notional, max_impact_pct,
                                        allow_partial)


def test_buy_fills_with_slippage(cfg, book):
    broker = PaperBroker(cfg.execution, _FakeClob(book))
    fill = broker.execute(Order(token_id="yes-token", side="BUY", price=0.50, size=100))
    assert fill is not None
    assert fill.side == "BUY"
    assert fill.price >= 0.50                      # החלקה חיובית לקנייה
    assert fill.price <= 0.50 * (1 + cfg.execution.slippage_bps / 10_000) + 1e-9
    assert fill.size == 100


def test_sell_fills_below_bid(cfg, book):
    broker = PaperBroker(cfg.execution, _FakeClob(book))
    fill = broker.execute(Order(token_id="yes-token", side="SELL", price=0.49, size=50))
    assert fill is not None and fill.price <= 0.49


def test_thin_book_rejects(cfg, book):
    thin = Book(token_id="t", best_bid=0.49, best_ask=0.50, bid_size=1, ask_size=1,
                bids=[(0.49, 1.0)], asks=[(0.50, 1.0)])
    broker = PaperBroker(cfg.execution, _FakeClob(thin))
    assert broker.execute(Order(token_id="t", side="BUY", price=0.50, size=5000)) is None


def test_no_book_rejects(cfg):
    broker = PaperBroker(cfg.execution, _FakeClob(None))
    assert broker.execute(Order(token_id="t", side="BUY", price=0.5, size=10)) is None


def test_fee_applied(cfg, book):
    """עמלת טאקר לפי הנוסחה הרשמית C × rate × p × (1−p)."""
    broker = PaperBroker(cfg.execution, _FakeClob(book))
    fill = broker.execute(Order(token_id="yes-token", side="BUY", price=0.50, size=100,
                                fee_rate=0.05))
    assert fill.fee > 0
    expected = 100 * 0.05 * fill.price * (1 - fill.price)
    assert abs(fill.fee - round(expected, 5)) < 1e-6


def test_maker_style_market_pays_no_fee(cfg, book):
    """שוק פטור מעמלה (geopolitics) ⇒ אפס עמלה."""
    broker = PaperBroker(cfg.execution, _FakeClob(book))
    fill = broker.execute(Order(token_id="yes-token", side="BUY", price=0.50, size=100,
                                fee_rate=0.0))
    assert fill.fee == 0.0


def test_flat_fee_mode_still_available(cfg, book):
    cfg.execution.fee_mode = "off"
    cfg.execution.taker_fee_bps = 100
    broker = PaperBroker(cfg.execution, _FakeClob(book))
    fill = broker.execute(Order(token_id="yes-token", side="BUY", price=0.50, size=100))
    assert abs(fill.fee - fill.notional * 0.01) < 1e-6


def test_aggressive_exit_fills_partially(cfg):
    """ספר דק: פקודת FAK רגילה מתבטלת, יציאה אגרסיבית ממלאת מה שיש."""
    thin = Book(token_id="t", best_bid=0.40, best_ask=0.42, bid_size=20, ask_size=20,
                bids=[(0.40, 20.0), (0.38, 30.0)], asks=[(0.42, 20.0)])
    broker = PaperBroker(cfg.execution, _FakeClob(thin))

    normal = broker.execute(Order(token_id="t", side="SELL", price=0.40, size=500))
    assert normal is None

    partial = broker.execute(Order(token_id="t", side="SELL", price=0.40, size=500),
                             aggressive=True)
    assert partial is not None
    assert 0 < partial.size < 500          # מילאה חלק, לא הכל
    assert partial.price <= 0.40


def test_aggressive_exit_still_respects_bounds(cfg):
    empty = Book(token_id="t", best_bid=0.40, best_ask=0.42, bid_size=0, ask_size=0,
                 bids=[], asks=[])
    broker = PaperBroker(cfg.execution, _FakeClob(empty))
    assert broker.execute(Order(token_id="t", side="SELL", price=0.40, size=100),
                          aggressive=True) is None
