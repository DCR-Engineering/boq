"""Viewport separation.

A single drawing sheet carries several independent drawings plus legend copies of the same
marks. On DCR2564 sheet ST-02 a naive count of C1..C4 mark strings returns 44; the true figure
is 20 columns, drawn twice (foundation plan and columns & beams plan), plus one legend copy of
each mark in the column schedule.

Counting anything without separating viewports first is wrong. These helpers split a set of
words into spatial clusters using the natural whitespace gutters between drawings.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .words import Word


@dataclass(frozen=True, slots=True)
class Cluster:
    """A spatially separated group of words."""

    lo: float
    hi: float
    words: tuple[Word, ...]

    def __len__(self) -> int:
        return len(self.words)


def find_gaps(values: list[float], min_gap: float) -> list[float]:
    """Midpoints of every gap in ``values`` wider than ``min_gap``.

    These are the split lines between viewports.
    """
    ordered = sorted(values)
    return [(lo + hi) / 2 for lo, hi in pairwise(ordered) if hi - lo > min_gap]


def split(words: list[Word], axis: str, min_gap: float) -> list[Cluster]:
    """Split words into clusters along ``axis`` ("x" or "y") at every gap wider than ``min_gap``.

    Clusters are returned in increasing coordinate order.
    """
    if axis not in ("x", "y"):
        raise ValueError(f"axis must be 'x' or 'y', got {axis!r}")
    if not words:
        return []

    key = (lambda w: w.x) if axis == "x" else (lambda w: w.y)
    ordered = sorted(words, key=key)

    clusters: list[Cluster] = []
    current: list[Word] = [ordered[0]]
    for prev, cur in pairwise(ordered):
        if key(cur) - key(prev) > min_gap:
            clusters.append(_finish(current, key))
            current = []
        current.append(cur)
    clusters.append(_finish(current, key))
    return clusters


def _finish(words: list[Word], key) -> Cluster:
    return Cluster(lo=min(key(w) for w in words), hi=max(key(w) for w in words), words=tuple(words))


def largest_cluster(clusters: list[Cluster]) -> Cluster:
    """The cluster holding the most words -- usually the main drawing."""
    if not clusters:
        raise ValueError("no clusters")
    return max(clusters, key=len)
