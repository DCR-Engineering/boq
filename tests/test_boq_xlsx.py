"""BoQ workbook writer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.rates.library import RateLibrary
from boq.report import boq_xlsx
from boq.rules import engine
from boq.rules.factors import Factors
from boq.text.words import load_words

FIXTURES = Path(__file__).parent / "fixtures" / "DCR2564"

SET_A_WINDOWS = {
    "W01": 2,
    "W02": 3,
    "W03": 2,
    "W05": 1,
    "W06": 2,
    "W07": 1,
    "W08": 1,
    "W09": 1,
    "W10": 2,
    "W13": 1,
    "W14": 1,
    "W15": 1,
    "W16": 2,
    "W17": 2,
}

PRICED_LIBRARY = {
    "version": "test-1",
    "currency": "BHD",
    "decimals": 3,
    "items": [
        {
            "code": "BLK.200",
            "description": "200mm thermal block",
            "unit": "m2",
            "supply_and_fix": {"low": 5.2, "expected": 5.75, "high": 6.4},
        },
        {
            "code": "PLS.EXT",
            "description": "External plaster",
            "unit": "m2",
            "supply_and_fix": {"expected": 2.25},
        },
    ],
    "mapping": {"block.external.area": "BLK.200", "finish.plaster.external": "PLS.EXT"},
}


@pytest.fixture(scope="module")
def result():
    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text(encoding="utf-8"))
    thermal = thermal_calc.parse(CellMap.from_dict(payload["sheets"]))
    areas = area_schedule.parse(load_words(FIXTURES / "arch_p05_area_schedule.words.json"))
    return engine.run(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project={"project_no": "DCR2564", "title": "Proposed Two Storey Villa"},
        source_files=[
            {"file": "THERMAL_DCR2564.xlsx", "sha256": "b" * 64, "set": "C", "file_type": "xlsx"}
        ],
    )


@pytest.fixture(scope="module")
def unpriced_book(result, tmp_path_factory):
    path = tmp_path_factory.mktemp("boq") / "unpriced.xlsx"
    info = boq_xlsx.write(result, path, rates=RateLibrary.from_dict({}))
    return info, _load(path)


@pytest.fixture(scope="module")
def priced_book(result, tmp_path_factory):
    path = tmp_path_factory.mktemp("boq") / "priced.xlsx"
    info = boq_xlsx.write(
        result,
        path,
        rates=RateLibrary.from_dict(PRICED_LIBRARY),
        factors=Factors.from_dict({"version": "t", "wastage": {"blockwork": 0.05}}),
    )
    return info, _load(path)


def _load(path):
    import openpyxl

    return openpyxl.load_workbook(path)


# -- structure ------------------------------------------------------------------------


def test_summary_is_the_first_sheet(unpriced_book):
    _, wb = unpriced_book
    assert wb.sheetnames[0] == "Summary"


def test_required_sheets_present(unpriced_book):
    _, wb = unpriced_book
    for name in ("Summary", "Assumptions", "Exclusions", "Rate Version"):
        assert name in wb.sheetnames


def test_trade_sheets_created_for_populated_trades(unpriced_book):
    info, wb = unpriced_book
    assert "Blockwork" in wb.sheetnames
    assert "Doors & Windows" in wb.sheetnames
    assert "Thermal" in wb.sheetnames
    assert info.trade_sheets


def test_empty_trades_are_skipped(unpriced_book):
    """No plumbing or electrical items exist yet, so those sheets are not written."""
    _, wb = unpriced_book
    assert "Plumbing" not in wb.sheetnames
    assert "Electrical" not in wb.sheetnames


# -- formulas live in the sheet ----------------------------------------------------------


def test_quantity_is_a_formula_not_a_precomputed_number(priced_book):
    _, wb = priced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 8).value == f"=F{row}*(1+G{row})"


def test_amount_is_a_formula(priced_book):
    _, wb = priced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 10).value == f"=H{row}*I{row}"


def test_net_quantity_is_stored_net_of_wastage(priced_book):
    _, wb = priced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 6).value == pytest.approx(529.606)
    assert ws.cell(row, 7).value == pytest.approx(0.05)


def test_trade_total_is_a_sum_formula(priced_book):
    _, wb = priced_book
    ws = wb["Blockwork"]
    totals = [
        ws.cell(r, 10).value
        for r in range(1, ws.max_row + 1)
        if isinstance(ws.cell(r, 10).value, str) and ws.cell(r, 10).value.startswith("=SUM(")
    ]
    assert totals, "trade sheet has no SUM total"


def test_summary_pulls_trade_totals_by_reference(priced_book):
    _, wb = priced_book
    ws = wb["Summary"]
    refs = [
        ws.cell(r, 2).value
        for r in range(1, ws.max_row + 1)
        if isinstance(ws.cell(r, 2).value, str) and ws.cell(r, 2).value.startswith("='")
    ]
    assert any("Blockwork" in r for r in refs)


# -- pricing -------------------------------------------------------------------------------


def test_priced_rate_is_written(priced_book):
    _, wb = priced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 9).value == pytest.approx(5.75)


def test_price_level_selects_the_band(result, tmp_path):
    path = tmp_path / "low.xlsx"
    boq_xlsx.write(result, path, rates=RateLibrary.from_dict(PRICED_LIBRARY), level="low")
    import openpyxl

    ws = openpyxl.load_workbook(path)["Blockwork"]
    assert ws.cell(_find_row(ws, "block.external.area"), 9).value == pytest.approx(5.2)


def test_unpriced_items_say_rate_required_not_a_number(unpriced_book):
    info, wb = unpriced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 9).value == "RATE REQUIRED"
    assert ws.cell(row, 10).value in (None, "")
    assert info.rate_required_count > 0
    assert info.priced_count == 0


def test_no_invented_prices_anywhere_in_an_unpriced_workbook(unpriced_book):
    """Guardrail: with an empty library, not one numeric rate may appear."""
    _, wb = unpriced_book
    for name in wb.sheetnames:
        if name in ("Summary", "Assumptions", "Exclusions", "Rate Version"):
            continue
        ws = wb[name]
        for row in range(4, ws.max_row + 1):
            value = ws.cell(row, 9).value
            assert not isinstance(value, int | float), f"{name}!I{row} has an invented rate"


# -- unavailable quantities -------------------------------------------------------------------


def test_unavailable_items_have_no_quantity_and_carry_the_reason(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Superstructure Concrete"]
    row = _find_row(ws, "conc.slab.pt.first")
    assert ws.cell(row, 6).value == "-"
    assert ws.cell(row, 8).value in (None, "")
    assert "NOT AVAILABLE" in ws.cell(row, 14).value
    assert "PT SPECIALIST" in ws.cell(row, 14).value


def test_exclusions_sheet_lists_every_unavailable_item(unpriced_book, result):
    info, wb = unpriced_book
    ws = wb["Exclusions"]
    listed = {ws.cell(r, 1).value for r in range(1, ws.max_row + 1)}
    for item in result.unavailable:
        assert item.id in listed
    assert info.unavailable_count == len(result.unavailable)


def test_exclusions_carry_reason_codes(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Exclusions"]
    codes = {ws.cell(r, 4).value for r in range(1, ws.max_row + 1)}
    assert {"not-issued", "needs-plan-geometry", "extractor-not-built"} <= codes


# -- assumptions and provenance ------------------------------------------------------------------


def test_assumptions_sheet_lists_derived_items_with_formulas(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Assumptions"]
    rows = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    assert "finish.plaster.external" in rows
    assert "x 2 faces" in ws.cell(rows["finish.plaster.external"], 6).value


def test_every_row_records_its_source(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert "THERMAL_DCR2564.xlsx" in ws.cell(row, 13).value


def test_rate_version_sheet_records_the_library(priced_book):
    _, wb = priced_book
    ws = wb["Rate Version"]
    values = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
    assert values["Rate library version"] == "test-1"
    assert values["Currency"] == "BHD"
    assert values["Pricing basis"] == "supply_and_fix"


def test_empty_library_is_announced_on_the_rate_version_sheet(unpriced_book):
    _, wb = unpriced_book
    text = " ".join(
        str(wb["Rate Version"].cell(r, 1).value) for r in range(1, wb["Rate Version"].max_row + 1)
    )
    assert "rate library is empty" in text.lower()


def test_summary_reports_export_is_blocked(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Summary"]
    values = {ws.cell(r, 1).value: ws.cell(r, 2).value for r in range(1, ws.max_row + 1)}
    assert values["Exportable"].startswith("NO")
    assert values["Rate library version"] == "0.0.0"


def test_summary_lists_cross_checks(unpriced_book):
    _, wb = unpriced_book
    ws = wb["Summary"]
    ids = {ws.cell(r, 1).value for r in range(1, ws.max_row + 1)}
    assert "envelope_decomposition" in ids
    assert "thermal_spreadsheet_errors" in ids


def _find_row(ws, item_id: str) -> int:
    for row in range(1, ws.max_row + 1):
        if ws.cell(row, 1).value == item_id:
            return row
    raise AssertionError(f"{item_id} not found in {ws.title}")


# -- the formulas must actually compute, not merely look like formulas ----------------


def _recalculate(path: Path, out_dir: Path) -> Path:
    """Recalculate a workbook with LibreOffice and return the rewritten file."""
    import shutil
    import subprocess

    soffice = shutil.which("libreoffice") or shutil.which("soffice")
    if soffice is None:
        pytest.skip("LibreOffice not installed; cannot evaluate embedded formulas")
    subprocess.run(
        [
            soffice,
            "--headless",
            "--calc",
            "--convert-to",
            "xlsx:Calc MS Excel 2007 XML",
            "--outdir",
            str(out_dir),
            str(path),
        ],
        check=True,
        capture_output=True,
        timeout=240,
    )
    return out_dir / path.name


@pytest.mark.integration
def test_embedded_formulas_evaluate_to_the_right_numbers(result, tmp_path):
    """End to end: write, recalculate in a real spreadsheet engine, read the values back."""
    import openpyxl

    src = tmp_path / "calc_check.xlsx"
    boq_xlsx.write(
        result,
        src,
        rates=RateLibrary.from_dict(PRICED_LIBRARY),
        factors=Factors.from_dict({"version": "t", "wastage": {"blockwork": 0.05}}),
    )
    recalculated = _recalculate(src, tmp_path / "out")
    wb = openpyxl.load_workbook(recalculated, data_only=True)

    ws = wb["Blockwork"]
    row = _find_row(ws, "block.external.area")
    assert ws.cell(row, 8).value == pytest.approx(529.606 * 1.05)
    assert ws.cell(row, 10).value == pytest.approx(529.606 * 1.05 * 5.75)

    # Finishes carries no wastage key, so quantity passes through unchanged.
    fin = wb["Finishes"]
    frow = _find_row(fin, "finish.plaster.external")
    assert fin.cell(frow, 10).value == pytest.approx(1059.212 * 2.25)

    # The Summary total is the sum of the trade sheets, resolved across sheets.
    summary = wb["Summary"]
    total = next(
        summary.cell(r, 2).value
        for r in range(1, summary.max_row + 1)
        if summary.cell(r, 1).value == "TOTAL"
    )
    assert total == pytest.approx(529.606 * 1.05 * 5.75 + 1059.212 * 2.25)
