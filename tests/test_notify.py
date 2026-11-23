"""התראות: נכשלות בשקט, לא מציפות, ולא זורקות."""
import json

from pmmb.notify import Notifier, fmt_daily, fmt_entry, fmt_exit, fmt_halt


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("PMMB_TELEGRAM_TOKEN", raising=False)
    monkeypatch.delenv("PMMB_TELEGRAM_CHAT_ID", raising=False)
    n = Notifier(token="", chat_id="")
    assert not n.enabled
    assert n.send("test") is False        # לא זורק, לא מנסה רשת


def test_send_posts_json(monkeypatch):
    calls = []

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok":true}'

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    n = Notifier(token="T", chat_id="C", min_interval_sec=0)
    assert n.send("שלום", force=True) is True
    assert n.sent == 1
    body = json.loads(calls[0].data.decode())
    assert body["chat_id"] == "C" and body["text"] == "שלום"


def test_duplicate_suppressed(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen",
                        lambda *a, **k: type("R", (), {
                            "__enter__": lambda s: s, "__exit__": lambda *a: False,
                            "read": lambda s: b"{}"})())
    n = Notifier(token="T", chat_id="C", min_interval_sec=0)
    assert n.send("אותה הודעה", force=True) is True
    assert n.send("אותה הודעה") is False      # כפילות
def test_failure_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    n = Notifier(token="T", chat_id="C", min_interval_sec=0)
    assert n.send("x", force=True) is False
    assert n.failed == 1


def test_formatters():
    assert "כניסה" in fmt_entry("paper", "Q?", 0.42, 100, 0.8, 0.03)
    assert "יציאה" in fmt_exit("paper", "Q?", 0.5, 12.5, "יעד")
    assert "עצר" in fmt_halt("live", "drawdown", 900.0)
    assert "סיכום יומי" in fmt_daily("paper", 1000.0, 5.0, 3)
    assert "🔻" in fmt_exit("paper", "Q?", 0.5, -3.0, "סטופ")
