"""Row reconstruction: turn scattered words back into table rows.

The core algorithm (docs/template-analysis.md section 4): cluster words whose baselines are
within a tolerance of each other, then sort each cluster left to right.

The tolerance matters. On the DCR2564 area schedule a single logical row is split across
y-buckets 3 pt apart -- "FIRST FLOOR 170.8 SQ.M. 41.3 %" sits on one baseline while its net
buildable figure "154.6" sits on another. A naive exact-y grouping loses the association.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from .words import Word

DEFAULT_Y_TOLERANCE = 5.0


@dataclass(frozen=True, slots=True)
class Row:
    """Words sharing a baseline, ordered left to right."""

    y: float
    words: tuple[Word, ...]

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    def cells(self, min_gap: float) -> list[str]:
        """Split the row into cells wherever the horizontal gap exceeds ``min_gap``.

        Uses the gap between the end of one word and the start of the next. Falls back to
        the inter-word start distance for words with no recorded width.
        """
        if not self.words:
            return []
        out: list[list[str]] = [[self.words[0].text]]
        for prev, cur in pairwise(self.words):
            edge = prev.x1 if prev.x1 is not None else prev.x
            if cur.x - edge > min_gap:
                out.append([cur.text])
            else:
                out[-1].append(cur.text)
        return [" ".join(c) for c in out]

    def find(self, text: str) -> Word | None:
        """First word exactly matching ``text``."""
        return next((w for w in self.words if w.text == text), None)


def group_rows(words: list[Word], tolerance: float = DEFAULT_Y_TOLERANCE) -> list[Row]:
    """Group words into rows by vertical proximity.

    Greedy single-pass clustering over y-sorted words: a word joins the current row while it
    is within ``tolerance`` of that row's *first* word, which keeps a long row from drifting
    downward one small step at a time.
    """
    if not words:
        return []

    rows: list[Row] = []
    current: list[Word] = []
    anchor = 0.0

    for word in sorted(words, key=lambda w: (w.y, w.x)):
        if current and word.y - anchor > tolerance:
            rows.append(_finish(current))
            current = []
        if not current:
            anchor = word.y
        current.append(word)

    if current:
        rows.append(_finish(current))
    return rows


def _finish(words: list[Word]) -> Row:
    ordered = tuple(sorted(words, key=lambda w: w.x))
    return Row(y=min(w.y for w in words), words=ordered)


def rows_in_region(
    words: list[Word],
    *,
    x_min: float = float("-inf"),
    x_max: float = float("inf"),
    y_min: float = float("-inf"),
    y_max: float = float("inf"),
    tolerance: float = DEFAULT_Y_TOLERANCE,
) -> list[Row]:
    """Rows built only from words inside a bounding box.

    Used to isolate a schedule from the rest of the sheet before parsing it -- a drawing sheet
    carries several unrelated tables plus the title block.
    """
    selected = [w for w in words if x_min <= w.x <= x_max and y_min <= w.y <= y_max]
    return group_rows(selected, tolerance=tolerance)
