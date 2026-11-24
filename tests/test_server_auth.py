"""Security regression tests for the HTTP dashboard bind and API authentication."""
from __future__ import annotations

import pytest

from pmmb.server import _is_loopback_address, make_handler, serve, token_ok


@pytest.mark.parametrize("address", ["127.0.0.1", "::1", "127.0.0.2"])
def test_loopback_addresses_are_local(address):
    assert _is_loopback_address(address)


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "192.0.2.10", "dashboard.example", "localhost"])
def test_non_loopback_and_unknown_addresses_are_not_local(address):
    assert not _is_loopback_address(address)


def test_empty_token_never_authenticates():
    assert token_ok("anything", "") is False
    assert token_ok("", "secret") is False
    assert token_ok("wrong", "secret") is False
    assert token_ok("secret", "secret") is True


def test_missing_token_only_authorizes_loopback_clients(monkeypatch, cfg):
    monkeypatch.setenv("PMMB_STATUS_TOKEN", "")
    handler_type = make_handler(
        cfg, max_age_sec=60, refresh_sec=30, token="", trader=object()
    )
    local = object.__new__(handler_type)
    local.client_address = ("127.0.0.1", 12345)
    remote = object.__new__(handler_type)
    remote.client_address = ("198.51.100.12", 12345)

    assert local._authorized({})
    assert not remote._authorized({})


def test_public_bind_is_rejected_without_token(monkeypatch, cfg):
    monkeypatch.setenv("PMMB_STATUS_TOKEN", "")
    with pytest.raises(ValueError, match="PMMB_STATUS_TOKEN"):
        serve(cfg, host="0.0.0.0", port=0)


def test_loopback_bind_works_without_token(monkeypatch, cfg):
    monkeypatch.setenv("PMMB_STATUS_TOKEN", "")
    httpd = serve(cfg, host="127.0.0.1", port=0)
    try:
        assert httpd.server_address[1] > 0
    finally:
        httpd.server_close()


def test_public_bind_works_with_environment_token(monkeypatch, cfg):
    monkeypatch.setenv("PMMB_STATUS_TOKEN", "test-token-that-is-not-a-real-secret")
    httpd = serve(cfg, host="0.0.0.0", port=0)
    try:
        assert httpd.server_address[1] > 0
    finally:
        httpd.server_close()


def test_dashboard_source_forwards_token_to_api_and_csv_links():
    from pathlib import Path

    ui_source = (Path(__file__).resolve().parents[1] / "src" / "pmmb" / "ui.py").read_text(encoding="utf-8")
    assert 'new URLSearchParams(window.location.hash.replace(/^#/, ""))' in ui_source
    assert 'const STATUS_TOKEN = tokenFromHash || tokenFromQuery || ""' in ui_source
    assert 'window.history.replaceState' in ui_source
    assert '"X-Token": STATUS_TOKEN' in ui_source
    assert 'function downloadTradesCsv()' in ui_source
    assert ui_source.count('onclick="downloadTradesCsv()"') == 3
    assert 'authUrl("/api/export/trades.csv")' not in ui_source


def test_access_token_is_redacted_from_http_logs():
    from pmmb.server import _redact_token_from_log

    log_line = '"GET /?token=do-not-log-this HTTP/1.1" 200 -'
    redacted = _redact_token_from_log(log_line)
    assert "do-not-log-this" not in redacted
    assert "token=[REDACTED]" in redacted


def test_auth_header_takes_precedence_over_route_token_query(cfg):
    handler_type = make_handler(
        cfg, max_age_sec=60, refresh_sec=30, token="dashboard-secret", trader=object()
    )
    handler = object.__new__(handler_type)
    handler.client_address = ("203.0.113.10", 12345)

    # /api/chart uses ?token= for a market token ID. The auth header must win.
    handler.headers = {"X-Token": "dashboard-secret"}
    assert handler._authorized({"token": ["polymarket-market-token-id"]})

    # A bad explicit header must not be rescued by a token-looking query value.
    handler.headers = {"X-Token": "wrong"}
    assert not handler._authorized({"token": ["dashboard-secret"]})

    # The query token remains available for the initial browser navigation.
    handler.headers = {}
    assert handler._authorized({"token": ["dashboard-secret"]})


def test_unauthenticated_dashboard_bootstrap_is_empty_and_api_stays_protected(cfg):
    handler_type = make_handler(
        cfg, max_age_sec=60, refresh_sec=30, token="dashboard-secret", trader=object()
    )
    handler = object.__new__(handler_type)
    handler.client_address = ("198.51.100.12", 12345)
    handler.headers = {}
    responses = []

    def capture(code, body, content_type, **_kwargs):
        responses.append((code, body, content_type))

    handler._send = capture
    handler.path = "/"
    handler._handle_get(head_only=False)
    assert responses[-1][0] == 200
    assert responses[-1][2].startswith("text/html")
    html = responses[-1][1].decode("utf-8")
    assert "dashboard-secret" not in html
    assert "account-equity-secret" not in html
    assert "window.__PMMB_INIT__ = {};" in html

    handler.path = "/api/state"
    handler._handle_get(head_only=False)
    assert responses[-1][0] == 401
