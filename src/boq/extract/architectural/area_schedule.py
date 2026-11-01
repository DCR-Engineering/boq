"""Area schedule extractor (Set A, sheet N04).

Parses the "Schedule of built-up areas & municipal built-up percentage" table. See
docs/template-analysis.md section 5.1.

This table is fully self-checking -- seven internal arithmetic identities hold exactly -- which
makes it the best regression fixture in the project and a genuine confidence signal at runtime.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from boq.text.rows import Row, group_rows
from boq.text.words import Word

# Floor rows carry a leading label; detail rows are numbered "1.", "2.", "3.".
_FLOOR_LABELS = ("GROUND FLOOR", "FIRST FLOOR", "SECOND FLOOR", "ROOF DECK", "TOP ROOF")
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_DETAIL = re.compile(r"^(\d+)\.$")
# Tokens that are units or explicit-absence markers, never part of a detail's name.
_NOISE = frozenset({"SQ.M.", "SQ.M", "N/A", "%"})


@dataclass
class FloorArea:
    name: str
    built_up: float | None
    municipal_pct: float | None
    net_buildable: float | None
    details: dict[str, float | None] = field(default_factory=dict)


@dataclass
class AreaSchedule:
    floors: list[FloorArea]
    total_built_up: float | None
    total_municipal_pct: float | None
    total_net_buildable: float | None
    plot_area: float | None

    def check(self, tol: float = 0.05) -> list[str]:
        """Run the table's internal arithmetic identities.

        Returns a list of human-readable failures; empty means the table is self-consistent.

        Percentages follow the office convention, established from DCR2564: each floor's
        percentage is net buildable / plot area **truncated** to one decimal, and the total is
        the sum of those truncated values. Rounding instead of truncating is wrong on two of
        the three floors (132.5 / 373.6 = 35.4657 %, printed as 35.4, not 35.5), and
        recomputing the total directly is wrong too (336.2 / 373.6 = 89.99 %, printed 89.8).
        """
        problems: list[str] = []

        for floor in self.floors:
            details = [v for v in floor.details.values() if v is not None]
            if details and floor.built_up is not None:
                got = sum(details)
                if abs(got - floor.built_up) > tol:
                    problems.append(
                        f"{floor.name}: details sum to {got:.1f} "
                        f"but built-up is {floor.built_up:.1f}"
                    )

        for label, values, total in (
            ("built-up", [f.built_up for f in self.floors], self.total_built_up),
            ("net buildable", [f.net_buildable for f in self.floors], self.total_net_buildable),
            ("municipal %", [f.municipal_pct for f in self.floors], self.total_municipal_pct),
        ):
            present = [v for v in values if v is not None]
            if present and total is not None:
                got = sum(present)
                if abs(got - total) > tol:
                    problems.append(f"{label}: floors sum to {got:.1f} but total is {total:.1f}")

        if self.plot_area and self.total_net_buildable:
            for floor in self.floors:
                if floor.net_buildable is None or floor.municipal_pct is None:
                    continue
                expected = _trunc1(floor.net_buildable / self.plot_area * 100)
                if abs(expected - floor.municipal_pct) > 0.05:
                    problems.append(
                        f"{floor.name}: {floor.net_buildable} / {self.plot_area} = "
                        f"{expected:.1f}% but sheet states {floor.municipal_pct:.1f}%"
                    )

        return problems


def _trunc1(value: float) -> float:
    """Truncate to one decimal place -- the office's percentage convention (see check())."""
    return math.floor(value * 10) / 10


def _numbers(row: Row) -> list[tuple[float, float]]:
    """(value, x) for every numeric token in the row, left to right."""
    return [(float(w.text), w.x) for w in row.words if _NUMBER.match(w.text)]


def parse(words: list[Word], tolerance: float = 5.0) -> AreaSchedule:
    """Parse the area schedule from the positioned words of sheet N04.

    Column assignment is by x-position, which is what makes this robust: the built-up,
    municipal-percentage and net-buildable columns occupy stable horizontal bands even though
    document order interleaves them unpredictably.
    """
    rows = group_rows(words, tolerance=tolerance)

    floors: list[FloorArea] = []
    total = FloorArea("TOTAL", None, None, None)
    plot_area: float | None = None
    current: FloorArea | None = None

    # Column bands are derived from the header row rather than hard-coded, so a sheet plotted
    # at a different size still parses. Fall back to the observed bands if the header is absent.
    pct_x, net_x = _column_bands(rows)

    for row in rows:
        text = row.text.upper()

        if "PLOT" in text and "AREA" in text:
            nums = _numbers(row)
            if nums:
                plot_area = nums[-1][0]
            continue

        label = next((f for f in _FLOOR_LABELS if text.startswith(f)), None)
        if label:
            current = _build(label, _numbers(row), pct_x, net_x)
            floors.append(current)
            continue

        if text.startswith("TOTAL"):
            total = _build("TOTAL", _numbers(row), pct_x, net_x)
            current = None
            continue

        detail = _DETAIL.match(row.words[0].text) if row.words else None
        if detail and current is not None:
            name_parts = [
                w.text for w in row.words[1:] if not _NUMBER.match(w.text) and w.text not in _NOISE
            ]
            name = " ".join(name_parts).strip()
            nums = _numbers(row)
            # "GARAGE N/A" carries no number -- record the detail with a null, do not drop it.
            current.details[name] = nums[0][0] if nums else None

    return AreaSchedule(
        floors=floors,
        total_built_up=total.built_up,
        total_municipal_pct=total.municipal_pct,
        total_net_buildable=total.net_buildable,
        plot_area=plot_area,
    )


def _column_bands(rows: list[Row]) -> tuple[float, float]:
    """x thresholds separating built-up | municipal % | net buildable."""
    pct_x, net_x = 400.0, 540.0
    for row in rows:
        pct = row.find("PERCENTAGE")
        buildable = row.find("BUILDABLE")
        if pct is not None and buildable is not None:
            pct_x = pct.x - 40
            net_x = buildable.x - 10
            break
    return pct_x, net_x


def _build(name: str, nums: list[tuple[float, float]], pct_x: float, net_x: float) -> FloorArea:
    built_up = next((v for v, x in nums if x < pct_x), None)
    municipal = next((v for v, x in nums if pct_x <= x < net_x), None)
    net = next((v for v, x in nums if x >= net_x), None)
    return FloorArea(name=name, built_up=built_up, municipal_pct=municipal, net_buildable=net)
