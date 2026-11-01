"""Footing schedule extractor (Set B, sheet ST-02).

A conventional row-per-mark table once the sheet's 270-degree rotation is undone. See
docs/template-analysis.md section 6.2.

The important property is what it does *not* give: ``L`` reads "SEE PLAN" for every mark, so
a footing's volume cannot be computed from this schedule. The extractor records that as a
missing length with a reason rather than inventing one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from boq.text.rows import Row, group_rows
from boq.text.words import Word

_MARK = re.compile(r"^(SF|F|PC|CF)\d+$", re.IGNORECASE)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
# "6T16" / "8T16" -> count and diameter; "T16@150" -> diameter and spacing.
_BARS = re.compile(r"^(\d+)[TY](\d+)$", re.IGNORECASE)
_SPACED = re.compile(r"^[TYR](\d+)@(\d+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class BarSpec:
    raw: str
    count: int | None = None
    diameter_mm: int | None = None
    spacing_mm: int | None = None

    @classmethod
    def parse(cls, text: str) -> BarSpec | None:
        token = text.strip()
        if not token or token == "-":
            return None
        if m := _BARS.match(token):
            return cls(raw=token, count=int(m.group(1)), diameter_mm=int(m.group(2)))
        if m := _SPACED.match(token):
            return cls(raw=token, diameter_mm=int(m.group(1)), spacing_mm=int(m.group(2)))
        return cls(raw=token)


@dataclass
class Footing:
    mark: str
    length_mm: float | None
    length_note: str | None
    width_mm: float | None
    depth_mm: float | None
    bottom_main: BarSpec | None
    bottom_transverse: BarSpec | None
    top_main: BarSpec | None
    top_transverse: BarSpec | None
    remarks: str | None

    @property
    def has_length(self) -> bool:
        return self.length_mm is not None

    def volume_m3(self) -> float | None:
        """Concrete volume, or None when the schedule does not give a length."""
        if not (self.length_mm and self.width_mm and self.depth_mm):
            return None
        return self.length_mm * self.width_mm * self.depth_mm / 1e9

    @property
    def missing_reason(self) -> str | None:
        if self.has_length:
            return None
        note = self.length_note or "not stated"
        return (
            f"footing {self.mark}: the schedule gives L as '{note}', so the run length must "
            f"come from plan geometry"
        )


@dataclass
class FootingSchedule:
    footings: list[Footing]

    def mark(self, mark: str) -> Footing | None:
        return next((f for f in self.footings if f.mark.upper() == mark.upper()), None)

    @property
    def marks(self) -> list[str]:
        return [f.mark for f in self.footings]

    def missing_lengths(self) -> list[str]:
        return [f.missing_reason for f in self.footings if f.missing_reason]


def parse(words: list[Word], tolerance: float = 4.0) -> FootingSchedule:
    """Parse the footing schedule from the positioned words of sheet ST-02."""
    region = _locate(words)
    rows = group_rows(region, tolerance=tolerance)

    footings: list[Footing] = []
    for row in rows:
        if not row.words or not _MARK.match(row.words[0].text):
            continue
        footings.append(_footing(row))
    return FootingSchedule(footings=footings)


def _locate(words: list[Word]) -> list[Word]:
    """Words belonging to the footing schedule block.

    Anchored on the *adjacent* words "FOOTING SCHEDULE". Anchoring on a whole text row would
    be wrong: a drawing sheet is wide, and unrelated plan annotation sitting at the same
    baseline hundreds of points away would drag the region's left edge across the sheet.
    """
    anchor = _caption(words, "FOOTING", "SCHEDULE")
    if anchor is None:
        return words

    x_min = anchor.x - 40
    x_max = anchor.x + 320
    y_min = anchor.y - 5
    return [w for w in words if x_min <= w.x <= x_max and y_min <= w.y <= y_min + 120]


def _caption(words: list[Word], first: str, second: str, max_gap: float = 40.0) -> Word | None:
    """The first word of an adjacent ``first second`` caption, if present."""
    firsts = [w for w in words if w.text.upper() == first]
    seconds = [w for w in words if w.text.upper() == second]
    for a in firsts:
        for b in seconds:
            if abs(b.y - a.y) <= 4 and 0 < b.x - a.x <= max_gap:
                return a
    return None


def _footing(row: Row) -> Footing:
    cells = row.cells(min_gap=9)
    mark = cells[0]
    rest = cells[1:]

    length_mm: float | None = None
    length_note: str | None = None
    numbers: list[float] = []
    bars: list[str] = []
    remarks: str | None = None

    for cell in rest:
        upper = cell.upper()
        if "SEE PLAN" in upper:
            length_note = "SEE PLAN"
            # "SEE PLAN 1000" is one cell when the gap is tight: keep the trailing number.
            tail = upper.replace("SEE PLAN", "").strip()
            if _NUMBER.match(tail):
                numbers.append(float(tail))
            continue
        if upper in ("CONCENTRIC", "ECCENTRIC"):
            remarks = upper.capitalize()
            continue
        for token in cell.split():
            if _NUMBER.match(token):
                numbers.append(float(token))
            elif token != "-":
                bars.append(token)
            else:
                bars.append("-")

    width_mm = numbers[0] if len(numbers) > 0 else None
    depth_mm = numbers[1] if len(numbers) > 1 else None

    specs = [BarSpec.parse(b) for b in bars]
    specs += [None] * (4 - len(specs))

    return Footing(
        mark=mark,
        length_mm=length_mm,
        length_note=length_note,
        width_mm=width_mm,
        depth_mm=depth_mm,
        bottom_main=specs[0],
        bottom_transverse=specs[1],
        top_main=specs[2],
        top_transverse=specs[3],
        remarks=remarks,
    )
