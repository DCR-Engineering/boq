"""Column schedule extractor (Set B, sheet ST-02).

A **transposed** table: the marks run across the top as columns, and each attribute is a row
beneath them. Values belong to a mark by horizontal band, not by reading order -- document
order delivers this schedule as three disconnected runs (all bar callouts, then all marks,
then all dimensions), which is the sharpest case for positional reconstruction in the whole
project. See docs/template-analysis.md section 6.1.

The sheet is plotted with ``/Rotate 270``; ``words_from_pdf`` undoes that before this runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from boq.text.rows import group_rows
from boq.text.words import Word

_MARK = re.compile(r"^(C\d+|BC|PC\d+|SC\d+)$")
_NUMBER = re.compile(r"^\d+$")
_TOTAL_BARS = re.compile(r"^(\d+)[TY](\d+)$", re.IGNORECASE)
_LINKS = re.compile(r"^(\d*)[TYR](\d+)@(\d+)", re.IGNORECASE)
# "06 Y 16mm" arrives as three tokens.
_DIA_TOKEN = re.compile(r"^(\d+)mm$", re.IGNORECASE)


@dataclass
class Column:
    mark: str
    width_mm: int | None = None
    depth_mm: int | None = None
    bar_count: int | None = None
    bar_diameter_mm: int | None = None
    links_at_support: str | None = None
    links_at_midspan: str | None = None
    links: list[str] = field(default_factory=list)

    @property
    def section_mm(self) -> str | None:
        if self.width_mm is None or self.depth_mm is None:
            return None
        return f"{self.width_mm}x{self.depth_mm}"

    @property
    def area_m2(self) -> float | None:
        if self.width_mm is None or self.depth_mm is None:
            return None
        return self.width_mm * self.depth_mm / 1e6

    def volume_m3(self, height_m: float, count: int = 1) -> float | None:
        """Concrete volume for ``count`` columns of this type at ``height_m``."""
        area = self.area_m2
        return None if area is None else area * height_m * count


@dataclass
class ColumnSchedule:
    columns: list[Column]

    def mark(self, mark: str) -> Column | None:
        return next((c for c in self.columns if c.mark.upper() == mark.upper()), None)

    @property
    def marks(self) -> list[str]:
        return [c.mark for c in self.columns]


def parse(words: list[Word], tolerance: float = 3.0) -> ColumnSchedule:
    """Parse the transposed column schedule from the positioned words of sheet ST-02."""
    header = _header_row(words, tolerance)
    if header is None:
        return ColumnSchedule(columns=[])

    marks = [(w.text, w.x, w.x1 or w.x) for w in header]
    bands = _bands(marks)

    columns = {m: Column(mark=m) for m, _, _ in marks}

    # The attribute block sits below the mark row. Bound it on x as well as y: the ground
    # slab schedule shares this band of the sheet and would otherwise be read as column data.
    y_top = min(w.y for w in header)
    x_lo = min(lo for _, lo, _ in bands)
    x_hi = max(hi for _, _, hi in bands)
    body = [w for w in words if y_top < w.y <= y_top + 135 and x_lo <= w.x <= x_hi]

    for row in group_rows(body, tolerance=tolerance):
        _consume(row.words, bands, columns)

    _assign_links(words, bands, columns, y_top)
    return ColumnSchedule(columns=[columns[m] for m, _, _ in marks])


def _assign_links(words: list[Word], bands, columns: dict[str, Column], y_top: float) -> None:
    """Split the two rows of link callouts into support and midspan.

    Which row is which is read from the sheet's own ``SUPP.`` / ``MIDS.`` row labels rather
    than assumed from order.
    """
    labels = {
        w.text.upper().rstrip("."): w.y
        for w in words
        if w.text.upper().rstrip(".") in ("SUPP", "MIDS") and w.y > y_top
    }
    if "SUPP" not in labels or "MIDS" not in labels:
        return

    for name, lo, hi in bands:
        col = columns[name]
        for word in words:
            if not (lo <= word.x < hi) or not _LINKS.match(word.text):
                continue
            if abs(word.y - labels["SUPP"]) <= 3:
                col.links_at_support = col.links_at_support or word.text
            elif abs(word.y - labels["MIDS"]) <= 3:
                col.links_at_midspan = col.links_at_midspan or word.text


def _header_row(words: list[Word], tolerance: float) -> list[Word] | None:
    """The row holding the schedule's mark labels.

    Mark text is scattered all over a foundation plan -- ST-02 carries 27 ``BC`` labels and
    40 ``C*`` labels on its two plans -- so "the row with the most marks" picks a plan, not
    the schedule. The schedule is instead located by its ``VERTICAL`` reinforcement
    callouts, which appear nowhere else on the sheet, and the mark row is the nearest row
    above that cluster within the same horizontal span.
    """
    anchors = [w for w in words if w.text.upper() == "VERTICAL"]
    if len(anchors) < 2:
        return None

    x_lo = min(w.x for w in anchors) - 60
    x_hi = max(w.x1 or w.x for w in anchors) + 60
    y_lo = min(w.y for w in anchors)

    best: list[Word] | None = None
    best_y = -1.0
    for row in group_rows([w for w in words if w.y < y_lo], tolerance=tolerance):
        marks = [w for w in row.words if _MARK.match(w.text) and x_lo <= w.x <= x_hi]
        if len({w.text for w in marks}) < 2 or len(marks) != len({w.text for w in marks}):
            continue  # a schedule header lists each mark exactly once
        if row.y > best_y:
            best, best_y = marks, row.y
    return best


def _bands(marks: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Horizontal band owned by each mark, split at the midpoints between neighbours.

    The outermost bands are bounded by half the typical mark spacing rather than left open.
    An unbounded outer band swallows whatever else shares that strip of the sheet -- here,
    the ground slab schedule sitting to the right of C4.
    """
    ordered = sorted(marks, key=lambda m: m[1])
    if len(ordered) == 1:
        name, x0, x1 = ordered[0]
        return [(name, x0 - 30, x1 + 30)]

    gaps = [ordered[i + 1][1] - ordered[i][1] for i in range(len(ordered) - 1)]
    margin = (sorted(gaps)[len(gaps) // 2]) / 2

    out: list[tuple[str, float, float]] = []
    for i, (name, x0, x1) in enumerate(ordered):
        lo = x0 - margin if i == 0 else (ordered[i - 1][1] + x0) / 2
        hi = x1 + margin if i == len(ordered) - 1 else (ordered[i + 1][1] + x1) / 2
        out.append((name, lo, hi))
    return out


def _owner(x: float, bands: list[tuple[str, float, float]]) -> str | None:
    return next((name for name, lo, hi in bands if lo <= x < hi), None)


def _consume(words: list[Word], bands, columns: dict[str, Column]) -> None:
    """Assign one row's tokens to their owning mark."""
    pending_count: dict[str, int] = {}

    for word in words:
        owner = _owner(word.x, bands)
        if owner is None:
            continue
        col = columns[owner]
        token = word.text

        if m := _TOTAL_BARS.match(token):
            # "12T16": total count and diameter in one token.
            col.bar_count = col.bar_count or int(m.group(1))
            col.bar_diameter_mm = col.bar_diameter_mm or int(m.group(2))
        elif _LINKS.match(token):
            if token not in col.links:
                col.links.append(token)
        elif m := _DIA_TOKEN.match(token):
            # "16mm" completes a "06 Y 16mm" triple.
            col.bar_diameter_mm = col.bar_diameter_mm or int(m.group(1))
            if owner in pending_count:
                col.bar_count = col.bar_count or pending_count.pop(owner)
        elif _NUMBER.match(token):
            value = int(token)
            if value <= 40:
                # A small bare number before "Y 16mm" is the bar count.
                pending_count[owner] = value
            else:
                _add_dimension(col, value)


def _add_dimension(col: Column, value: int) -> None:
    """Section dimensions arrive as two bare numbers; the smaller is the width."""
    if col.width_mm is None and col.depth_mm is None:
        col.width_mm = value
        return
    if col.depth_mm is None:
        if value < col.width_mm:
            col.width_mm, col.depth_mm = value, col.width_mm
        else:
            col.depth_mm = value
