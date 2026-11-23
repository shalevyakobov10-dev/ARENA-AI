"""כלכלת הסקטורים: פטור מעמלה עדיף, ומדידה גוברת על הנחה."""
import pytest

from pmmb.feeview import fee_markdown, fee_table


def test_geopolitics_is_best_verdict():
    rows = {r.sector: r for r in fee_table()}
    assert rows["geopolitics"].rate == 0.0
    assert rows["geopolitics"].rt_fee == 0.0
    assert "✅" in rows["geopolitics"].verdict


def test_five_percent_sectors_need_thicker_edge():
    rows = {r.sector: r for r in fee_table(edge=0.025)}
    assert rows["sports"].breakeven > rows["geopolitics"].breakeven
    assert "❌" in rows["sports"].verdict


def test_thick_edge_makes_expensive_sector_viable():
    rows = {r.sector: r for r in fee_table(edge=0.06)}
    assert "✅" in rows["sports"].verdict


def test_measured_edge_overrides_default():
    rows = {r.sector: r for r in fee_table(edge=0.025, measured_edges={"macro": 0.005})}
    assert rows["macro"].edge == pytest.approx(0.005)
    assert "❌" in rows["macro"].verdict


def test_markdown_contains_formula_and_all_sectors():
    md = fee_markdown(fee_table(), spread=0.01, edge=0.025, price=0.5)
    assert "rate × p × (1 − p)" in md
    for sector in ("geopolitics", "sports", "politics"):
        assert sector in md


def test_report_file_written(tmp_path):
    from pmmb.feeview import write_fee_report

    p = write_fee_report(tmp_path / "fees.md", fee_table(), spread=0.01, edge=0.025, price=0.5)
    assert p.exists() and "כלכלת העמלות" in p.read_text(encoding="utf-8")
