"""Row reconstruction tests.

These guard the single most important behaviour in the project: that scattered AutoCAD text
is reassembled by position, not by document order.
"""

from __future__ import annotations

from boq.text.rows import group_rows, rows_in_region
from boq.text.words import Word


def test_empty_input():
    assert group_rows([]) == []


def test_words_are_ordered_left_to_right_not_by_input_order():
    # Deliberately supplied in scrambled order, as an AutoCAD plot would emit them.
    words = [Word(300, 10, "THIRD"), Word(100, 10, "FIRST"), Word(200, 10, "SECOND")]
    (row,) = group_rows(words)
    assert row.text == "FIRST SECOND THIRD"


def test_rows_separated_beyond_tolerance():
    words = [Word(10, 10, "a"), Word(10, 100, "b")]
    rows = group_rows(words, tolerance=5)
    assert [r.text for r in rows] == ["a", "b"]


def test_near_baselines_merge_within_tolerance():
    """The real case from the DCR2564 area schedule: one logical row, two baselines 3 pt apart."""
    words = [Word(201, 252, "FIRST"), Word(229, 252, "FLOOR"), Word(564, 255, "154.6")]
    (row,) = group_rows(words, tolerance=5)
    assert row.text == "FIRST FLOOR 154.6"


def test_tolerance_anchors_to_row_start_so_long_rows_do_not_drift():
    """Successive 4 pt steps must not chain into one row under a 5 pt tolerance."""
    words = [Word(10, 0, "a"), Word(20, 4, "b"), Word(30, 8, "c"), Word(40, 12, "d")]
    rows = group_rows(words, tolerance=5)
    assert len(rows) > 1, "greedy chaining would have merged all four into a single row"
    assert rows[0].text == "a b"


def test_cells_split_on_horizontal_gaps():
    words = [
        Word(10, 0, "GROUND", x1=50),
        Word(52, 0, "FLOOR", x1=80),
        Word(300, 0, "170.8", x1=330),
    ]
    (row,) = group_rows(words)
    assert row.cells(min_gap=20) == ["GROUND FLOOR", "170.8"]


def test_rows_in_region_filters_before_grouping():
    words = [Word(10, 10, "keep"), Word(10, 900, "titleblock")]
    rows = rows_in_region(words, y_max=500)
    assert [r.text for r in rows] == ["keep"]


def test_find_returns_matching_word():
    (row,) = group_rows([Word(10, 0, "PERCENTAGE"), Word(90, 0, "AREA")])
    assert row.find("AREA").x == 90
    assert row.find("MISSING") is None
