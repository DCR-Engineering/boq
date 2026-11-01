"""Thermal calculation extractor (Set C).

Parses the EWA thermal-insulation workbook. See docs/template-analysis.md section 7.

This is the single richest file in a project. It is the **only** source of window and door
dimensions -- the Set A schedules are cards with no dimension strings in their text layer --
and the best source of external wall areas, given per elevation and per floor.

Two defects in the DCR2564 sample shape this module:

* sheet 'CAL BEAMS' holds live ``#REF!`` cells, so every read is error-aware;
* the 'window' sheet's mark labels are shifted one row against their dimension rows from W13
  onward. The dimensions, counts and totals are unaffected -- the glazed total is still
  correct -- but mark-to-area mapping from that sheet is unreliable. Openings are therefore
  read from 'Main', and the shift is reported as a defect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .workbook import CellMap, ErrorCell

ELEVATIONS = ("front", "rear", "left", "right")

# Sheet names as the office's template spells them. 'BEAM ' carries a trailing space.
SHEET_GLASS = "DETAILS OF GLASS SELECTED"
SHEET_MAIN = "Main"
SHEET_WALL = "wall"
SHEET_WINDOW = "window"

# 'Main' opening rows: mark, then the two dimensions, then a count per elevation.
_MAIN_OPENING_ROWS = range(18, 46)
_MAIN_MARK_COL = "A"
_MAIN_DIM_COLS = ("B", "C")
_MAIN_COUNT_COLS = {"front": "D", "rear": "F", "left": "H", "right": "J"}

# 'wall' sheet: per floor, (length, height, area) for each elevation.
_WALL_ROWS = range(10, 15)
_WALL_COLS = {
    "front": ("B", "C", "D"),
    "rear": ("E", "F", "G"),
    "left": ("H", "I", "J"),
    "right": ("K", "L", "M"),
}
_WALL_TOTAL_ROW = 16
_WALL_TOTAL_COLS = {"front": "D", "rear": "G", "left": "J", "right": "M"}

# 'window' sheet, used only to detect the label shift -- never as a quantity source.
_WINDOW_ROWS = range(13, 46)

# Envelope element sheets: (sheet, cell holding the stated area).
_ENVELOPE_SHEETS = {
    "roof": ("ROOF", None),
    "external_walls": ("WALLS", "G14"),
    "external_columns": ("COLUMNS", "G14"),
    "external_beams": ("BEAM ", "H14"),
    "ceilings": ("CEILINGS", "H14"),
}


@dataclass(frozen=True, slots=True)
class Opening:
    """A window or door, with its size and per-elevation counts."""

    mark: str
    width_m: float
    height_m: float
    counts: dict[str, int]

    @property
    def total_count(self) -> int:
        return sum(self.counts.values())

    @property
    def unit_area_m2(self) -> float:
        return self.width_m * self.height_m

    @property
    def area_m2(self) -> float:
        return self.unit_area_m2 * self.total_count

    @property
    def is_door(self) -> bool:
        return self.mark.upper().startswith(("D", "SD", "GD"))


@dataclass(frozen=True, slots=True)
class WallArea:
    floor: str
    elevation: str
    length_m: float | None
    height_m: float | None
    area_m2: float | None


@dataclass(frozen=True, slots=True)
class EnvelopeElement:
    name: str
    u_value: float | None
    area_m2: float | None


@dataclass
class Defect:
    """A problem found in the source workbook, reported rather than worked around."""

    code: str
    detail: str
    blocking: bool = False

    def __str__(self) -> str:
        return f"[{self.code}] {self.detail}"


@dataclass
class ThermalCalc:
    declared_glass_area_m2: float | None
    declared_surface_area_m2: float | None
    declared_glazing_ratio: float | None
    openings: list[Opening] = field(default_factory=list)
    wall_areas: list[WallArea] = field(default_factory=list)
    declared_wall_totals: dict[str, float | None] = field(default_factory=dict)
    envelope: dict[str, EnvelopeElement] = field(default_factory=dict)
    header: dict[str, str | None] = field(default_factory=dict)
    defects: list[Defect] = field(default_factory=list)
    error_cells: list[ErrorCell] = field(default_factory=list)

    # -- derived, computed in plain code, never by a model --------------------------

    @property
    def computed_glass_area_m2(self) -> float:
        return sum(o.area_m2 for o in self.openings)

    @property
    def computed_window_area_m2(self) -> float:
        return sum(o.area_m2 for o in self.openings if not o.is_door)

    @property
    def computed_wall_area_m2(self) -> float:
        return sum(w.area_m2 for w in self.wall_areas if w.area_m2 is not None)

    @property
    def window_count(self) -> int:
        return sum(o.total_count for o in self.openings if not o.is_door)

    @property
    def glazed_door_count(self) -> int:
        return sum(o.total_count for o in self.openings if o.is_door)

    def opening(self, mark: str) -> Opening | None:
        return next((o for o in self.openings if o.mark.upper() == mark.upper()), None)

    def verify(self, tol: float = 0.01) -> list[Defect]:
        """Check the workbook's declared totals against values recomputed from its own inputs.

        Returns newly found defects; they are also appended to :attr:`defects`.
        """
        found: list[Defect] = []

        if self.declared_glass_area_m2 is not None and self.openings:
            computed = self.computed_glass_area_m2
            if abs(computed - self.declared_glass_area_m2) > tol:
                found.append(
                    Defect(
                        "glass-area-mismatch",
                        f"declared total glass area {self.declared_glass_area_m2:.3f} m2 but "
                        f"the openings in '{SHEET_MAIN}' sum to {computed:.3f} m2",
                        blocking=True,
                    )
                )

        if self.declared_surface_area_m2 is not None and self.wall_areas:
            computed = self.computed_wall_area_m2
            if abs(computed - self.declared_surface_area_m2) > tol:
                found.append(
                    Defect(
                        "wall-area-mismatch",
                        f"declared total surface area {self.declared_surface_area_m2:.3f} m2 "
                        f"but the '{SHEET_WALL}' sheet sums to {computed:.3f} m2",
                        blocking=True,
                    )
                )

        for elevation, declared in self.declared_wall_totals.items():
            if declared is None:
                continue
            computed = sum(
                w.area_m2
                for w in self.wall_areas
                if w.elevation == elevation and w.area_m2 is not None
            )
            if abs(computed - declared) > tol:
                found.append(
                    Defect(
                        "wall-elevation-mismatch",
                        f"{elevation}: declared {declared:.3f} m2, floors sum to {computed:.3f} m2",
                    )
                )

        self.defects.extend(found)
        return found


def parse(cells: CellMap) -> ThermalCalc:
    """Parse a thermal workbook into a :class:`ThermalCalc`."""
    calc = ThermalCalc(
        declared_glass_area_m2=cells.number(SHEET_GLASS, "E11"),
        declared_surface_area_m2=cells.number(SHEET_GLASS, "H11"),
        declared_glazing_ratio=cells.number(SHEET_GLASS, "J11"),
    )

    calc.error_cells = cells.errors()
    for err in calc.error_cells:
        calc.defects.append(
            Defect(
                "spreadsheet-error",
                f"{err} -- the value it feeds is unknown and must not be treated as zero",
                blocking=True,
            )
        )

    calc.header = _parse_header(cells)
    calc.openings = _parse_openings(cells)
    calc.wall_areas = _parse_wall_areas(cells)
    calc.declared_wall_totals = (
        {
            elev: cells.number(SHEET_WALL, f"{col}{_WALL_TOTAL_ROW}")
            for elev, col in _WALL_TOTAL_COLS.items()
        }
        if cells.has_sheet(SHEET_WALL)
        else {}
    )
    calc.envelope = _parse_envelope(cells)

    shift = _detect_window_sheet_shift(cells, calc.openings)
    if shift is not None:
        calc.defects.append(shift)

    calc.verify()
    return calc


# -- section parsers ------------------------------------------------------------------


def _parse_header(cells: CellMap) -> dict[str, str | None]:
    """Header fields from the EWA form, used for cross-checking against the drawings."""
    if not cells.has_sheet("ROOF"):
        return {}
    application = cells.text("ROOF", "B7")
    if application and "\n" in application:
        application = application.split("\n", 1)[1].strip()
    return {
        "application_no": application,
        "area": cells.text("ROOF", "G12"),
        "building_type": cells.text("ROOF", "A14"),
        "floors": cells.text("ROOF", "F14"),
    }


def _parse_openings(cells: CellMap) -> list[Opening]:
    """Openings with their sizes, from 'Main' -- the only place dimensions exist."""
    if not cells.has_sheet(SHEET_MAIN):
        return []

    openings: list[Opening] = []
    for row in _MAIN_OPENING_ROWS:
        mark = cells.text(SHEET_MAIN, f"{_MAIN_MARK_COL}{row}")
        if not mark or mark in {"0", "-"}:
            continue

        a = cells.number(SHEET_MAIN, f"{_MAIN_DIM_COLS[0]}{row}")
        b = cells.number(SHEET_MAIN, f"{_MAIN_DIM_COLS[1]}{row}")
        if not a or not b:
            continue

        counts = {
            elev: int(cells.number(SHEET_MAIN, f"{col}{row}") or 0)
            for elev, col in _MAIN_COUNT_COLS.items()
        }
        if sum(counts.values()) == 0:
            continue

        openings.append(Opening(mark=mark, width_m=a, height_m=b, counts=counts))
    return openings


def _parse_wall_areas(cells: CellMap) -> list[WallArea]:
    if not cells.has_sheet(SHEET_WALL):
        return []

    areas: list[WallArea] = []
    for row in _WALL_ROWS:
        floor = cells.text(SHEET_WALL, f"A{row}")
        if not floor or floor == "0":
            continue
        for elevation, (lcol, hcol, acol) in _WALL_COLS.items():
            area = cells.number(SHEET_WALL, f"{acol}{row}")
            if not area:
                continue
            areas.append(
                WallArea(
                    floor=floor,
                    elevation=elevation,
                    length_m=cells.number(SHEET_WALL, f"{lcol}{row}"),
                    height_m=cells.number(SHEET_WALL, f"{hcol}{row}"),
                    area_m2=area,
                )
            )
    return areas


def _parse_envelope(cells: CellMap) -> dict[str, EnvelopeElement]:
    """U-value and stated area per envelope element.

    The U-value is written into a free-text cell ("  U-Value = 0.54 W/m.2 o C"), so it is
    located by scanning the sheet for a cell containing "U-Value" and reading the number
    after the '='. If no number can be read the element records None rather than a guess.
    """
    out: dict[str, EnvelopeElement] = {}
    for name, (sheet, area_cell) in _ENVELOPE_SHEETS.items():
        if not cells.has_sheet(sheet):
            continue
        out[name] = EnvelopeElement(
            name=name,
            u_value=_find_u_value(cells, sheet),
            area_m2=cells.number(sheet, area_cell) if area_cell else None,
        )
    return out


def _find_u_value(cells: CellMap, sheet: str) -> float | None:
    for ref in cells.cell_refs(sheet):
        text = cells.text(sheet, ref)
        if not text or "u-value" not in text.lower() or "=" not in text:
            continue
        tail = text.split("=", 1)[1].strip()
        number = ""
        for ch in tail:
            if ch.isdigit() or (ch == "." and "." not in number):
                number += ch
            elif number:
                break
        if number:
            try:
                return float(number)
            except ValueError:
                return None
    return None


def _detect_window_sheet_shift(cells: CellMap, openings: list[Opening]) -> Defect | None:
    """Detect the 'window' sheet's label misalignment against 'Main'.

    Compares each mark's dimensions in the two sheets. A disagreement means the labels have
    drifted, so the 'window' sheet cannot be used to map glass area back to a mark.
    """
    if not cells.has_sheet(SHEET_WINDOW) or not openings:
        return None

    by_mark = {o.mark.upper(): o for o in openings}
    mismatched: list[str] = []
    seen: set[str] = set()

    for row in _WINDOW_ROWS:
        mark = cells.text(SHEET_WINDOW, f"A{row}")
        if not mark or mark in {"0", "-"}:
            continue
        w = cells.number(SHEET_WINDOW, f"C{row}")
        h = cells.number(SHEET_WINDOW, f"D{row}")
        if not w or not h:
            continue
        seen.add(mark.upper())
        ref = by_mark.get(mark.upper())
        if ref is not None and (abs(ref.width_m - w) > 1e-9 or abs(ref.height_m - h) > 1e-9):
            mismatched.append(
                f"{mark} is {ref.width_m}x{ref.height_m} in '{SHEET_MAIN}' "
                f"but {w}x{h} in '{SHEET_WINDOW}'"
            )

    missing = sorted(set(by_mark) - seen)
    if not mismatched and not missing:
        return None

    parts = []
    if missing:
        parts.append(f"marks absent from '{SHEET_WINDOW}': {', '.join(missing)}")
    if mismatched:
        parts.append("; ".join(mismatched))

    return Defect(
        "window-sheet-label-shift",
        f"'{SHEET_WINDOW}' labels disagree with '{SHEET_MAIN}' -- {' | '.join(parts)}. "
        f"Totals are unaffected, but mark-to-area mapping from '{SHEET_WINDOW}' is unreliable; "
        f"openings were read from '{SHEET_MAIN}'.",
    )
