"""Spreadsheet reading with explicit error handling.

Set C arrives as a real EWA thermal-insulation workbook, and the DCR2564 sample contains live
``#REF!`` cells (sheet 'CAL BEAMS'). Coercing those to zero would silently understate a
quantity, which is the exact failure the guardrails exist to prevent.

Everything here therefore distinguishes three states: a value, an *error* (the formula is
broken), and *absent* (the cell is empty).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Values openpyxl returns, with data_only=True, for a cached formula error.
ERROR_VALUES = frozenset(
    {"#REF!", "#VALUE!", "#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#SPILL!"}
)


class CellError(ValueError):
    """Raised when a cell required for a quantity holds a spreadsheet error."""

    def __init__(self, sheet: str, cell: str, value: str) -> None:
        super().__init__(f"{sheet}!{cell} holds {value}")
        self.sheet = sheet
        self.cell = cell
        self.value = value


def is_error(value: Any) -> bool:
    """True if ``value`` is a spreadsheet error marker."""
    return isinstance(value, str) and value.strip() in ERROR_VALUES


@dataclass(frozen=True, slots=True)
class ErrorCell:
    sheet: str
    cell: str
    value: str

    def __str__(self) -> str:
        return f"{self.sheet}!{self.cell} = {self.value}"


class CellMap:
    """Sheet name -> {cell reference -> value}, with error-aware accessors.

    Decouples the extractor from openpyxl so it can be exercised against a recorded cell map
    without carrying a client workbook in the repository.
    """

    def __init__(self, sheets: dict[str, dict[str, Any]]) -> None:
        self._sheets = sheets

    # -- construction ----------------------------------------------------------------

    @classmethod
    def from_xlsx(cls, path: str | Path) -> CellMap:
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True)
        try:
            sheets: dict[str, dict[str, Any]] = {}
            for ws in wb.worksheets:
                cells = {
                    c.coordinate: c.value
                    for row in ws.iter_rows()
                    for c in row
                    if c.value is not None and c.value != ""
                }
                sheets[ws.title] = cells
            return cls(sheets)
        finally:
            wb.close()

    @classmethod
    def from_dict(cls, sheets: dict[str, dict[str, Any]]) -> CellMap:
        return cls(sheets)

    # -- access ----------------------------------------------------------------------

    @property
    def sheet_names(self) -> list[str]:
        return list(self._sheets)

    def has_sheet(self, sheet: str) -> bool:
        return sheet in self._sheets

    def cell_refs(self, sheet: str) -> list[str]:
        """Every populated cell reference on ``sheet``, in sorted order."""
        return sorted(self._sheets.get(sheet, {}))

    def raw(self, sheet: str, cell: str) -> Any:
        """The stored value, error markers included, or None if absent."""
        return self._sheets.get(sheet, {}).get(cell)

    def value(self, sheet: str, cell: str) -> Any:
        """The value, or None if absent. Raises :class:`CellError` on a spreadsheet error."""
        raw = self.raw(sheet, cell)
        if is_error(raw):
            raise CellError(sheet, cell, raw.strip())
        return raw

    def number(self, sheet: str, cell: str) -> float | None:
        """Numeric value, or None if absent or non-numeric. Raises on a spreadsheet error.

        Never returns 0.0 as a stand-in for missing or broken data.
        """
        val = self.value(sheet, cell)
        if val is None:
            return None
        if isinstance(val, bool):
            return None
        if isinstance(val, int | float):
            return float(val)
        try:
            return float(str(val).strip())
        except ValueError:
            return None

    def text(self, sheet: str, cell: str) -> str | None:
        val = self.raw(sheet, cell)
        return None if val is None else str(val).strip()

    def errors(self) -> list[ErrorCell]:
        """Every error cell in the workbook, sheet order then cell order."""
        return [
            ErrorCell(sheet=name, cell=ref, value=str(val).strip())
            for name, cells in self._sheets.items()
            for ref, val in cells.items()
            if is_error(val)
        ]
