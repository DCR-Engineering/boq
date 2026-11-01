"""Thermal workbook extractor tests, against cells captured from the real DCR2564 file.

Expected values are those recorded in docs/template-analysis.md section 7.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellError, CellMap, is_error

FIXTURE = Path(__file__).parent / "fixtures" / "DCR2564" / "thermal_workbook.cells.json"


@pytest.fixture(scope="module")
def cells() -> CellMap:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return CellMap.from_dict(payload["sheets"])


@pytest.fixture(scope="module")
def calc(cells):
    return thermal_calc.parse(cells)


# -- declared headline figures ---------------------------------------------------------


def test_declared_glass_and_surface_areas(calc):
    assert calc.declared_glass_area_m2 == pytest.approx(146.93)
    assert calc.declared_surface_area_m2 == pytest.approx(814.816)
    assert calc.declared_glazing_ratio == pytest.approx(0.1803, abs=1e-4)


def test_glass_area_recomputes_to_the_declared_total(calc):
    """The central verification: 146.93 m2 must fall out of W x H x count."""
    assert calc.computed_glass_area_m2 == pytest.approx(146.93, abs=0.001)


def test_glazing_ratio_is_consistent(calc):
    ratio = calc.computed_glass_area_m2 / calc.declared_surface_area_m2
    assert ratio == pytest.approx(calc.declared_glazing_ratio, abs=1e-6)


# -- openings ---------------------------------------------------------------------------


def test_opening_count(calc):
    assert len(calc.openings) == 21


def test_windows_and_glazed_doors_split(calc):
    assert calc.window_count == 24
    assert calc.glazed_door_count == 5


@pytest.mark.parametrize(
    ("mark", "w", "h", "count", "area"),
    [
        ("W5", 3.3, 7.0, 1, 23.100),
        ("W6", 4.3, 2.8, 2, 24.080),
        ("W17", 4.3, 2.8, 1, 12.040),
        ("W16", 1.1, 1.4, 3, 4.620),
        ("SD1", 4.4, 2.8, 1, 12.320),
    ],
)
def test_individual_openings(calc, mark, w, h, count, area):
    o = calc.opening(mark)
    assert o is not None, f"{mark} not extracted"
    assert (o.width_m, o.height_m) == (w, h)
    assert o.total_count == count
    assert o.area_m2 == pytest.approx(area, abs=0.001)


def test_counts_are_summed_across_elevations(calc):
    w2 = calc.opening("W2")
    assert w2.counts == {"front": 0, "rear": 0, "left": 1, "right": 2}
    assert w2.total_count == 3


def test_doors_classified(calc):
    assert calc.opening("SD1").is_door
    assert calc.opening("D1").is_door
    assert not calc.opening("W1").is_door


# -- wall areas --------------------------------------------------------------------------


def test_wall_areas_per_floor_and_elevation(calc):
    assert len(calc.wall_areas) == 12  # 3 floors x 4 elevations
    gf_front = next(w for w in calc.wall_areas if w.floor == "Ground" and w.elevation == "front")
    assert (gf_front.length_m, gf_front.height_m) == (15.0, 4.48)
    assert gf_front.area_m2 == pytest.approx(67.2)


def test_wall_area_total(calc):
    assert calc.computed_wall_area_m2 == pytest.approx(814.816, abs=0.001)


def test_declared_elevation_totals(calc):
    assert calc.declared_wall_totals["front"] == pytest.approx(154.56)
    assert calc.declared_wall_totals["right"] == pytest.approx(251.552)


# -- envelope ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("element", "u_value", "area"),
    [
        ("roof", 0.26, None),
        ("external_walls", 0.54, 529.606),
        ("external_columns", 0.50, 98.4),
        ("external_beams", 0.50, 39.88),
        ("ceilings", 0.49, 0.0),
    ],
)
def test_envelope_u_values_and_areas(calc, element, u_value, area):
    el = calc.envelope[element]
    assert el.u_value == pytest.approx(u_value)
    if area is None:
        assert el.area_m2 is None
    else:
        assert el.area_m2 == pytest.approx(area)


# -- defects --------------------------------------------------------------------------------


def test_spreadsheet_errors_are_found_not_coerced(calc):
    """The real workbook has live #REF! cells in 'CAL BEAMS'."""
    refs = {f"{e.sheet}!{e.cell}" for e in calc.error_cells}
    assert "CAL BEAMS!E40" in refs
    assert "CAL BEAMS!K40" in refs
    assert all(e.value == "#REF!" for e in calc.error_cells)


def test_error_cells_raise_rather_than_return_zero(cells):
    with pytest.raises(CellError) as exc:
        cells.number("CAL BEAMS", "E40")
    assert exc.value.value == "#REF!"


def test_errors_reported_as_blocking_defects(calc):
    errs = [d for d in calc.defects if d.code == "spreadsheet-error"]
    assert errs and all(d.blocking for d in errs)


def test_window_sheet_label_shift_detected(calc):
    """W13 is missing from the 'window' sheet and later labels are shifted one row."""
    shift = next(d for d in calc.defects if d.code == "window-sheet-label-shift")
    assert "W13" in shift.detail
    assert not shift.blocking, "totals are unaffected, so this is not export-blocking"


def test_label_shift_is_not_a_quantity_error(calc):
    """Despite the shift, the glazed total is correct -- it must not be reported as wrong."""
    assert not [d for d in calc.defects if d.code == "glass-area-mismatch"]
    assert not [d for d in calc.defects if d.code == "wall-area-mismatch"]


# -- header, for cross-checking against the drawings ------------------------------------------


def test_header_fields_extracted(calc):
    assert calc.header["application_no"] == "DCR2503"
    assert calc.header["area"] == "BARBAR"


# -- the checker must bite ----------------------------------------------------------------------


def test_verify_detects_a_wrong_declared_total(cells):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["sheets"]["DETAILS OF GLASS SELECTED"]["E11"] = 120.0
    broken = thermal_calc.parse(CellMap.from_dict(payload["sheets"]))
    assert any(d.code == "glass-area-mismatch" and d.blocking for d in broken.defects)


def test_is_error_helper():
    assert is_error("#REF!")
    assert is_error("  #DIV/0! ")
    assert not is_error("0")
    assert not is_error(0)
    assert not is_error(None)
