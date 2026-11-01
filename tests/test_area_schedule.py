"""Area schedule regression test against the real DCR2564 sheet N04.

Exact-value test. The expected figures are the ones printed on the sheet, recorded in
docs/template-analysis.md section 5.1. If the positional reader regresses, these fail.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boq.extract.architectural import area_schedule
from boq.text.words import load_words

FIXTURE = Path(__file__).parent / "fixtures" / "DCR2564" / "arch_p05_area_schedule.words.json"


@pytest.fixture(scope="module")
def schedule():
    return area_schedule.parse(load_words(FIXTURE))


def test_plot_area(schedule):
    assert schedule.plot_area == 373.6


def test_floors_found(schedule):
    assert [f.name for f in schedule.floors] == ["GROUND FLOOR", "FIRST FLOOR", "ROOF DECK"]


@pytest.mark.parametrize(
    ("name", "built_up", "pct", "net"),
    [
        ("GROUND FLOOR", 170.8, 35.4, 132.5),
        ("FIRST FLOOR", 170.8, 41.3, 154.6),
        ("ROOF DECK", 65.3, 13.1, 49.1),
    ],
)
def test_floor_columns_assigned_by_position(schedule, name, built_up, pct, net):
    """The three numeric columns must not be transposed -- document order interleaves them."""
    floor = next(f for f in schedule.floors if f.name == name)
    assert (floor.built_up, floor.municipal_pct, floor.net_buildable) == (built_up, pct, net)


def test_totals(schedule):
    assert schedule.total_built_up == 406.9
    assert schedule.total_municipal_pct == 89.8
    assert schedule.total_net_buildable == 336.2


def test_ground_floor_details_including_the_null(schedule):
    gf = next(f for f in schedule.floors if f.name == "GROUND FLOOR")
    assert gf.details == {"MAIN VILLA": 132.5, "GARAGE": None, "SERVICES": 38.3}


def test_detail_rows_for_upper_floors(schedule):
    first = next(f for f in schedule.floors if f.name == "FIRST FLOOR")
    roof = next(f for f in schedule.floors if f.name == "ROOF DECK")
    assert first.details == {"VILLA": 154.6, "SERVICES": 16.2}
    assert roof.details == {"VILLA": 49.1, "SERVICES": 16.2}


def test_all_seven_arithmetic_identities_hold(schedule):
    """The sheet is self-checking; a clean parse must produce zero inconsistencies."""
    assert schedule.check() == []


def test_check_detects_a_corrupted_total(schedule):
    """The checker must actually bite, not vacuously pass."""
    import copy

    broken = copy.deepcopy(schedule)
    broken.total_built_up = 400.0
    problems = broken.check()
    assert any("built-up" in p for p in problems)


def test_percentage_convention_is_truncation_not_rounding(schedule):
    """Guards the office convention established in docs/template-analysis.md section 5.1.

    132.5 / 373.6 = 35.4657 %. The sheet prints 35.4, so the office truncates. If this check
    ever reverts to round(), two of the three floors raise false cross-check failures.
    """
    gf = next(f for f in schedule.floors if f.name == "GROUND FLOOR")
    raw = gf.net_buildable / schedule.plot_area * 100
    assert round(raw, 1) == 35.5, "precondition: rounding gives a different answer"
    assert gf.municipal_pct == 35.4
    assert schedule.check() == []
