"""Viewport separation tests.

Generic geometry, tested on synthetic layouts. The scenario mirrors the real trap documented
in docs/template-analysis.md section 6.6: one sheet carrying the same marks several times.
"""

from __future__ import annotations

import pytest

from boq.text.viewport import Cluster, find_gaps, largest_cluster, split
from boq.text.words import Word


def test_find_gaps_returns_midpoints():
    assert find_gaps([0, 1, 2, 100, 101], min_gap=10) == [51.0]


def test_find_gaps_ignores_small_separations():
    assert find_gaps([0, 5, 10], min_gap=10) == []


def test_split_rejects_bad_axis():
    with pytest.raises(ValueError, match="axis"):
        split([Word(0, 0, "a")], axis="z", min_gap=1)


def test_split_empty():
    assert split([], axis="x", min_gap=10) == []


def test_split_single_cluster_when_no_gap():
    words = [Word(0, 0, "a"), Word(5, 0, "b"), Word(10, 0, "c")]
    (cluster,) = split(words, axis="x", min_gap=50)
    assert len(cluster) == 3


def test_split_separates_two_viewports_on_y():
    """The ST-02 case: the same marks drawn twice, stacked vertically."""
    top = [Word(x, 100, "C1") for x in (10, 20, 30)]
    bottom = [Word(x, 900, "C1") for x in (10, 20, 30)]
    clusters = split(top + bottom, axis="y", min_gap=200)
    assert [len(c) for c in clusters] == [3, 3]
    assert clusters[0].lo == 100
    assert clusters[1].lo == 900


def test_split_preserves_every_word():
    words = [Word(0, 0, "a"), Word(500, 0, "b"), Word(1000, 0, "c")]
    clusters = split(words, axis="x", min_gap=100)
    assert sum(len(c) for c in clusters) == len(words)


def test_counting_without_separation_double_counts():
    """Demonstrates why viewport separation precedes any count."""
    marks = [Word(x, y, "C1") for y in (100, 900) for x in (10, 20)]
    assert len(marks) == 4  # naive count
    clusters = split(marks, axis="y", min_gap=200)
    assert len(largest_cluster(clusters)) == 2  # true per-plan count


def test_largest_cluster_raises_on_empty():
    with pytest.raises(ValueError, match="no clusters"):
        largest_cluster([])


def test_cluster_bounds():
    (cluster,) = split([Word(10, 0, "a"), Word(40, 0, "b")], axis="x", min_gap=100)
    assert isinstance(cluster, Cluster)
    assert (cluster.lo, cluster.hi) == (10, 40)
