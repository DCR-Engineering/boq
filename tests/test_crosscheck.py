"""Cross-check engine tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boq.crosscheck import checks
from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.text.words import load_words

FIXTURES = Path(__file__).parent / "fixtures" / "DCR2564"

# Set A window schedule, sheet A10. Quantities read by row alignment: the mark row and the
# QUANTITY row are positionally aligned left to right on each of the three card rows.
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

# The five renderings of the project number found across the document sets.
PROJECT_IDS = {
    "Set A title block": "DCR2564",
    "Set A header": "AUO-DCR 2564",
    "Set B header": "AUO-DCR 25564",
    "Set C application no": "DCR2503",
    "EWA form": "DCR2554",
}


@pytest.fixture(scope="module")
def thermal():
    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text(encoding="utf-8"))
    return thermal_calc.parse(CellMap.from_dict(payload["sheets"]))


@pytest.fixture(scope="module")
def areas():
    return area_schedule.parse(load_words(FIXTURES / "arch_p05_area_schedule.words.json"))


# -- mark normalisation -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("W01", "W1"),
        ("W1", "W1"),
        ("W8A", "W8"),
        ("W8B", "W8"),
        ("SD01", "SD1"),
        ("w10", "W10"),
        ("GD02", "GD2"),
    ],
)
def test_normalise_mark(raw, expected):
    assert checks.normalise_mark(raw) == expected


def test_normalise_does_not_merge_distinct_numbers():
    assert checks.normalise_mark("W1") != checks.normalise_mark("W10")


# -- checks that pass on the real sample ------------------------------------------------------


def test_area_schedule_passes(areas):
    r = checks.check_area_schedule_internal(areas)
    assert r.status == "pass"


def test_glass_area_passes(thermal):
    r = checks.check_glass_area(thermal)
    assert r.status == "pass"
    assert r.left == pytest.approx(146.93)
    assert r.right == pytest.approx(146.93)


def test_wall_area_passes(thermal):
    assert checks.check_wall_area(thermal).status == "pass"


# -- checks that fail on the real sample, as they should ----------------------------------------


def test_window_counts_fail_per_mark_despite_near_total(thermal):
    """The headline finding: six marks disagree while the totals differ by only two."""
    r = checks.check_window_counts(SET_A_WINDOWS, thermal)
    assert r.status == "fail"
    assert r.blocking
    assert (r.left, r.right) == (22, 24)
    for mark in ("W1", "W8", "W9", "W13", "W16", "W17"):
        assert f"{mark}:" in r.detail, f"{mark} mismatch not reported"
    assert "6 of 14 marks disagree" in r.detail


def test_window_counts_would_pass_a_totals_only_comparison(thermal):
    """Guards the design decision: totals-only comparison is not good enough here."""
    right = sum(o.total_count for o in thermal.openings if not o.is_door)
    assert abs(right - sum(SET_A_WINDOWS.values())) == 2
    # Yet six individual marks are wrong:
    assert checks.check_window_counts(SET_A_WINDOWS, thermal).status == "fail"


def test_spreadsheet_errors_block(thermal):
    r = checks.check_spreadsheet_errors(thermal)
    assert r.status == "fail"
    assert r.blocking
    assert r.left == 6
    assert "CAL BEAMS!E40" in r.detail


def test_project_identifiers_fail(thermal):
    r = checks.check_project_identifiers(PROJECT_IDS)
    assert r.status == "fail"
    assert "DCR2503" in r.detail


def test_project_identifiers_pass_when_consistent():
    r = checks.check_project_identifiers(
        {"Set A": "DCR2564", "Set B": "AUO-DCR 2564", "Set C": "2564"}
    )
    assert r.status == "pass"


def test_slab_spec_not_possible_when_pt_by_specialist(thermal):
    r = checks.check_slab_spec(None, thermal)
    assert r.status == "not_possible"
    assert r.blocking
    assert "specialist" in r.detail


# -- missing inputs are visible, not silently skipped ---------------------------------------------


def test_missing_inputs_are_reported():
    results = checks.run_all()
    assert {r.status for r in results} <= {"not_applicable", "not_possible"}
    assert len(results) == 7, "every check must appear even when its inputs are absent"


def test_window_check_not_possible_without_set_a(thermal):
    assert checks.check_window_counts(None, thermal).status == "not_possible"


# -- the runner ------------------------------------------------------------------------------------


def test_run_all_on_the_real_sample(areas, thermal):
    results = checks.run_all(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project_identifiers=PROJECT_IDS,
    )
    by_id = {r.check_id: r for r in results}
    assert by_id["area_schedule_internal"].status == "pass"
    assert by_id["glass_area_declared_vs_computed"].status == "pass"
    assert by_id["wall_area_declared_vs_computed"].status == "pass"
    assert by_id["window_count_setA_vs_setC"].status == "fail"
    assert by_id["thermal_spreadsheet_errors"].status == "fail"
    assert by_id["project_id_consistency"].status == "fail"
    assert by_id["slab_spec_structural_vs_thermal"].status == "not_possible"


def test_blocking_failures_gate_export(areas, thermal):
    results = checks.run_all(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project_identifiers=PROJECT_IDS,
    )
    blocking = checks.blocking_failures(results)
    ids = {r.check_id for r in blocking}
    assert ids == {
        "window_count_setA_vs_setC",
        "thermal_spreadsheet_errors",
        "slab_spec_structural_vs_thermal",
    }


def test_ok_property():
    assert checks.CheckResult("x", "d", "pass").ok
    assert checks.CheckResult("x", "d", "reconciled").ok
    assert not checks.CheckResult("x", "d", "fail").ok
