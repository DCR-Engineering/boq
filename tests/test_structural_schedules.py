"""Structural schedule extractor tests (Set B, sheet ST-02).

Exact-value tests against a fixture generated from the real STR2564.pdf. These are the two
regression tests promised in docs/proposed-structure.md section 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from boq.extract.structural import column_schedule, footing_schedule
from boq.text.words import load_words

FIXTURE = Path(__file__).parent / "fixtures" / "DCR2564" / "str_p05_schedules.words.json"


@pytest.fixture(scope="module")
def words():
    return load_words(FIXTURE)


@pytest.fixture(scope="module")
def footings(words):
    return footing_schedule.parse(words)


@pytest.fixture(scope="module")
def columns(words):
    return column_schedule.parse(words)


# -- footing schedule -----------------------------------------------------------------


def test_all_four_footing_marks_found(footings):
    assert footings.marks == ["SF1", "SF2", "SF3", "SF4"]


@pytest.mark.parametrize(
    ("mark", "width", "depth", "remarks"),
    [
        ("SF1", 1000, 400, "Concentric"),
        ("SF2", 1200, 400, "Concentric"),
        ("SF3", 1000, 400, "Eccentric"),
        ("SF4", 500, 400, "Eccentric"),
    ],
)
def test_footing_sections(footings, mark, width, depth, remarks):
    f = footings.mark(mark)
    assert (f.width_mm, f.depth_mm, f.remarks) == (width, depth, remarks)


def test_footing_bottom_reinforcement(footings):
    sf2 = footings.mark("SF2")
    assert sf2.bottom_main.count == 8
    assert sf2.bottom_main.diameter_mm == 16
    assert sf2.bottom_transverse.diameter_mm == 16
    assert sf2.bottom_transverse.spacing_mm == 150


def test_concentric_footings_have_no_top_steel(footings):
    for mark in ("SF1", "SF2"):
        assert footings.mark(mark).top_main is None


def test_eccentric_footings_carry_top_steel(footings):
    sf3 = footings.mark("SF3")
    sf4 = footings.mark("SF4")
    assert (sf3.top_main.count, sf3.top_main.diameter_mm) == (6, 16)
    assert (sf4.top_main.count, sf4.top_main.diameter_mm) == (6, 12)
    assert sf4.top_transverse.diameter_mm == 12


def test_length_is_see_plan_so_volume_is_unavailable(footings):
    """The headline limitation: this schedule cannot yield a footing volume."""
    for f in footings.footings:
        assert f.length_mm is None
        assert f.length_note == "SEE PLAN"
        assert f.volume_m3() is None
    assert len(footings.missing_lengths()) == 4
    assert "plan geometry" in footings.missing_lengths()[0]


def test_volume_computes_once_a_length_is_supplied(footings):
    import dataclasses

    sf1 = dataclasses.replace(footings.mark("SF1"), length_mm=5000.0)
    assert sf1.volume_m3() == pytest.approx(5.0 * 1.0 * 0.4)


# -- column schedule -------------------------------------------------------------------


def test_all_five_column_marks_found(columns):
    assert sorted(columns.marks) == ["BC", "C1", "C2", "C3", "C4"]


@pytest.mark.parametrize(
    ("mark", "width", "depth", "count", "dia"),
    [
        ("BC", 200, 300, 6, 12),
        ("C1", 200, 400, 6, 16),
        ("C2", 200, 500, 8, 16),
        ("C3", 200, 600, 12, 16),
        ("C4", 300, 600, 16, 20),
    ],
)
def test_column_sections_and_bars(columns, mark, width, depth, count, dia):
    """Exact values read off ST-02.

    This table is the reason positional extraction is non-negotiable: in document order the
    schedule arrives as three disconnected runs, and an earlier reading-order guess in
    docs/template-analysis.md assigned C1, C3 and BC to each other's sections.
    """
    c = columns.mark(mark)
    assert (c.width_mm, c.depth_mm) == (width, depth)
    assert (c.bar_count, c.bar_diameter_mm) == (count, dia)


@pytest.mark.parametrize(
    ("mark", "support", "midspan"),
    [
        ("BC", "T8@200C/C", "T8@200C/C"),
        ("C1", "T8@100C/C", "T8@200C/C"),
        ("C2", "2T8@100C/C", "2T8@200C/C"),
        ("C3", "2T8@100C/C", "2T8@150C/C"),
        ("C4", "2T10@100C/C", "2T10@150C/C"),
    ],
)
def test_links_split_by_the_sheets_own_labels(columns, mark, support, midspan):
    """Support and midspan come from the SUPP./MIDS. row labels, not from row order."""
    c = columns.mark(mark)
    assert c.links_at_support == support
    assert c.links_at_midspan == midspan


def test_column_areas(columns):
    assert columns.mark("C3").area_m2 == pytest.approx(0.12)
    assert columns.mark("C4").area_m2 == pytest.approx(0.18)


def test_column_volume_needs_a_height(columns):
    c3 = columns.mark("C3")
    assert c3.volume_m3(height_m=4.16, count=5) == pytest.approx(0.12 * 4.16 * 5)


def test_ground_slab_schedule_is_not_absorbed_into_c4(columns):
    """GS-1 sits immediately right of C4; an unbounded outer band would swallow it."""
    c4 = columns.mark("C4")
    assert (c4.width_mm, c4.depth_mm) == (300, 600)


def test_plan_mark_labels_do_not_hijack_the_header(columns):
    """ST-02 carries 27 BC and 40 C* labels on its plans; only the schedule row counts."""
    assert len(columns.columns) == 5


# -- fixture integrity ------------------------------------------------------------------


def test_reinforcement_callouts_survive_redaction(words):
    """Regression: an over-broad '@' redaction rule once destroyed every spacing callout."""
    texts = {w.text for w in words}
    assert "T16@150" in texts
    assert any(t.startswith("2T10@") for t in texts)


def test_fixture_contains_no_personal_data(words):
    blob = " ".join(w.text for w in words).lower()
    for token in ("balqees", "salwa", "marzooq", "almosawi", "iconeng", "+973", "epp/bn"):
        assert token not in blob
