"""BoQ workbook writer.

Build prompt section 8.1: one sheet per trade, plus Summary, Assumptions and Rate Version,
with **formulas living in the sheet** so the estimator can change a rate or a wastage
percentage and watch the totals move.

Nothing is pre-computed where a formula will do. Quantity, wastage, rate and amount are all
separate cells, and the amount is ``=qty*(1+wastage)*rate``, so the sheet is auditable by
reading it rather than by trusting this code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from boq.rates.library import Basis, Level, RateLibrary
from boq.rules.factors import Factors

if TYPE_CHECKING:
    from boq.normalize.items import QuantityItem

# Sheet order from the build prompt.
TRADE_SHEETS: list[tuple[str, str]] = [
    ("substructure", "Substructure"),
    ("superstructure_concrete", "Superstructure Concrete"),
    ("reinforcement", "Reinforcement"),
    ("blockwork", "Blockwork"),
    ("finishes", "Finishes"),
    ("doors_windows", "Doors & Windows"),
    ("thermal", "Thermal"),
    ("plumbing", "Plumbing"),
    ("drainage", "Drainage"),
    ("electrical", "Electrical"),
]

_HEADERS = [
    "Item ID",
    "Description",
    "Mark",
    "Level",
    "Unit",
    "Net Qty",
    "Wastage",
    "Qty",
    "Rate",
    "Amount",
    "Method",
    "Confidence",
    "Source",
    "Notes",
]
# Column letters matching _HEADERS.
_C = {
    name: chr(ord("A") + i)
    for i, name in enumerate(
        [
            "id",
            "desc",
            "mark",
            "level",
            "unit",
            "net",
            "wastage",
            "qty",
            "rate",
            "amount",
            "method",
            "confidence",
            "source",
            "notes",
        ]
    )
}

_RATE_REQUIRED = "RATE REQUIRED"


@dataclass
class WriteResult:
    path: Path
    trade_sheets: list[str]
    rate_required_count: int
    unavailable_count: int
    priced_count: int


def write(
    result,
    path: str | Path,
    *,
    rates: RateLibrary | None = None,
    factors: Factors | None = None,
    basis: Basis = "supply_and_fix",
    level: Level = "expected",
    project: dict[str, Any] | None = None,
) -> WriteResult:
    """Write ``result`` (an :class:`~boq.rules.engine.EngineResult`) as a BoQ workbook."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    rates = rates if rates is not None else RateLibrary.load()
    factors = factors or Factors.load()
    project = project or result.document.get("project", {})

    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    bold = Font(bold=True)
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    warn_fill = PatternFill("solid", fgColor="FFF2CC")
    null_fill = PatternFill("solid", fgColor="F2F2F2")
    money = f"#,##0.{'0' * rates.decimals}"

    by_trade = result.by_trade()
    matched = rates.match_all(result.items)

    written: list[tuple[str, str]] = []  # (sheet title, total cell)
    rate_required = 0
    priced = 0
    unavailable = 0

    for trade_key, title in TRADE_SHEETS:
        items = by_trade.get(trade_key, [])
        if not items:
            continue

        ws = wb.create_sheet(title[:31])
        ws.append([title])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([])
        ws.append(_HEADERS)
        for cell in ws[3]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", wrap_text=True)

        first_row = 4
        row = first_row
        for item in items:
            rated = matched[item.id]
            wastage = _wastage_for(item, factors)

            ws.cell(row, 1, item.id)
            ws.cell(row, 2, item.element)
            ws.cell(row, 3, item.mark or "")
            ws.cell(row, 4, item.level or "")
            ws.cell(row, 5, item.unit or "")

            if item.quantity is None:
                unavailable += 1
                ws.cell(row, 6, "-")
                ws.cell(row, 7, "")
                ws.cell(row, 8, "")
                ws.cell(row, 9, "")
                ws.cell(row, 10, "")
                for col in range(1, len(_HEADERS) + 1):
                    ws.cell(row, col).fill = null_fill
                ws.cell(row, 14, f"NOT AVAILABLE - {item.null_reason}")
            else:
                ws.cell(row, 6, item.quantity)
                ws.cell(row, 7, wastage).number_format = "0%"
                # Live formulas: the estimator edits Net Qty, Wastage or Rate and totals move.
                ws.cell(row, 8, f"={_C['net']}{row}*(1+{_C['wastage']}{row})")
                price = (
                    rated.rate.price(basis, level)
                    if rated.rate and not rated.rate_required
                    else None
                )
                if price is None:
                    rate_required += 1
                    ws.cell(row, 9, _RATE_REQUIRED)
                    ws.cell(row, 9).fill = warn_fill
                    ws.cell(row, 10, "")
                else:
                    priced += 1
                    ws.cell(row, 9, price).number_format = money
                    ws.cell(row, 10, f"={_C['qty']}{row}*{_C['rate']}{row}").number_format = money
                ws.cell(row, 8).number_format = "#,##0.000"
                ws.cell(row, 6).number_format = "#,##0.000"

            ws.cell(row, 11, item.method)
            ws.cell(row, 12, item.confidence).number_format = "0%"
            ws.cell(row, 13, _source_label(item))
            if item.quantity is not None:
                ws.cell(row, 14, _notes(item, rated))
            row += 1

        last_row = row - 1
        ws.cell(row + 1, 2, f"{title} total").font = bold
        total_cell = f"{_C['amount']}{row + 1}"
        ws.cell(
            row + 1, 10, f"=SUM({_C['amount']}{first_row}:{_C['amount']}{last_row})"
        ).font = bold
        ws.cell(row + 1, 10).number_format = money

        for idx, width in enumerate([28, 40, 8, 12, 7, 11, 9, 11, 12, 14, 12, 11, 34, 60], start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A4"
        written.append((ws.title, total_cell))

    _summary_sheet(wb, written, result, rates, project, money, bold, header_font, header_fill)
    _assumptions_sheet(wb, result, bold, header_font, header_fill)
    _exclusions_sheet(wb, result, bold, header_font, header_fill)
    _rate_version_sheet(wb, rates, factors, basis, level, bold, header_font, header_fill)

    # Summary first, so the workbook opens on the headline numbers.
    wb.move_sheet("Summary", offset=-wb.sheetnames.index("Summary"))

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)

    return WriteResult(
        path=out,
        trade_sheets=[t for t, _ in written],
        rate_required_count=rate_required,
        unavailable_count=unavailable,
        priced_count=priced,
    )


# -- supporting sheets ---------------------------------------------------------------


def _summary_sheet(wb, written, result, rates, project, money, bold, hfont, hfill) -> None:
    ws = wb.create_sheet("Summary")
    ws.append(["Bill of Quantities - Summary"])
    ws["A1"].font = __import__("openpyxl").styles.Font(bold=True, size=14)
    ws.append([])
    ws.append(["Project", project.get("project_no", "")])
    ws.append(["Title", project.get("title", "")])
    ws.append(["Currency", rates.currency])
    ws.append(["Rate library version", rates.version])
    ws.append(["Review status", result.document["extraction"].get("review_status", "draft")])
    ws.append(["Exportable", "YES" if result.exportable else "NO - blocking checks unresolved"])
    ws.append([])

    head = ws.max_row + 1
    ws.append(["Trade", "Amount"])
    for cell in ws[head]:
        cell.font = hfont
        cell.fill = hfill

    first = ws.max_row + 1
    for title, total_cell in written:
        ws.append([title, f"='{title}'!{total_cell}"])
        ws.cell(ws.max_row, 2).number_format = money
    last = ws.max_row

    ws.append([])
    ws.append(["TOTAL", f"=SUM(B{first}:B{last})" if written else 0])
    ws.cell(ws.max_row, 1).font = bold
    ws.cell(ws.max_row, 2).font = bold
    ws.cell(ws.max_row, 2).number_format = money

    ws.append([])
    ws.append(["Cross-checks"])
    ws.cell(ws.max_row, 1).font = bold
    head = ws.max_row + 1
    ws.append(["Check", "Status", "Blocking", "Detail"])
    for cell in ws[head]:
        cell.font = hfont
        cell.fill = hfill
    for check in result.cross_checks:
        ws.append(
            [
                check.check_id,
                check.status,
                "YES" if check.blocking and check.status in ("fail", "not_possible") else "",
                check.detail,
            ]
        )

    for col, width in (("A", 34), ("B", 18), ("C", 10), ("D", 100)):
        ws.column_dimensions[col].width = width


def _assumptions_sheet(wb, result, bold, hfont, hfill) -> None:
    """Assumed and derived items, with the formula that produced each."""
    ws = wb.create_sheet("Assumptions")
    ws.append(["Assumptions and derived quantities"])
    ws["A1"].font = bold
    ws.append(
        [
            "Every figure below was computed rather than read directly off a drawing. "
            "Review before this BoQ is issued."
        ]
    )
    ws.append([])
    head = ws.max_row + 1
    ws.append(
        [
            "Item ID",
            "Description",
            "Method",
            "Quantity",
            "Unit",
            "Formula",
            "Assumption ref",
            "Confidence",
            "Notes",
        ]
    )
    for cell in ws[head]:
        cell.font = hfont
        cell.fill = hfill

    for item in result.items:
        if item.method not in ("assumed", "derived"):
            continue
        ws.append(
            [
                item.id,
                item.element,
                item.method,
                item.quantity,
                item.unit or "",
                item.formula or "",
                item.assumption_ref or "",
                item.confidence,
                item.notes,
            ]
        )

    for col, width in (
        ("A", 30),
        ("B", 36),
        ("C", 11),
        ("D", 12),
        ("E", 7),
        ("F", 42),
        ("G", 18),
        ("H", 11),
        ("I", 70),
    ):
        ws.column_dimensions[col].width = width


def _exclusions_sheet(wb, result, bold, hfont, hfill) -> None:
    """Quantities that could not be taken off, and why -- the honest other half of a BoQ."""
    ws = wb.create_sheet("Exclusions")
    ws.append(["Quantities not included, and why"])
    ws["A1"].font = bold
    ws.append(
        [
            "These are not priced. A reason code of 'not-issued' or 'needs-plan-geometry' is a "
            "property of the issued documents; 'extractor-not-built' is a limitation of the "
            "take-off tool."
        ]
    )
    ws.append([])
    head = ws.max_row + 1
    ws.append(["Item ID", "Description", "Unit", "Reason code", "Reason", "Source"])
    for cell in ws[head]:
        cell.font = hfont
        cell.fill = hfill

    for item in result.unavailable:
        ws.append(
            [
                item.id,
                item.element,
                item.unit or "",
                item.flags[0] if item.flags else "",
                item.null_reason or "",
                _source_label(item),
            ]
        )

    for col, width in (("A", 30), ("B", 36), ("C", 7), ("D", 22), ("E", 90), ("F", 32)):
        ws.column_dimensions[col].width = width


def _rate_version_sheet(wb, rates, factors, basis, level, bold, hfont, hfill) -> None:
    ws = wb.create_sheet("Rate Version")
    ws.append(["Rate library and factors"])
    ws["A1"].font = bold
    ws.append([])
    for label, value in (
        ("Rate library version", rates.version),
        ("Effective date", rates.effective_date or "not stated"),
        ("Currency", rates.currency),
        ("Decimal places", rates.decimals),
        ("Pricing basis", basis),
        ("Price level", level),
        ("Rates in library", len(rates)),
        ("Factors version", factors.version or "not stated"),
    ):
        ws.append([label, value])

    ws.append([])
    if rates.is_empty:
        ws.append(
            [
                "The rate library is empty. Every quantity is flagged RATE REQUIRED. "
                "Prices are never invented by this tool."
            ]
        )
        ws.cell(ws.max_row, 1).font = bold
    else:
        head = ws.max_row + 1
        ws.append(["Code", "Description", "Unit", "Supplier", "Quoted on", "Source note"])
        for cell in ws[head]:
            cell.font = hfont
            cell.fill = hfill
        for code in rates.codes():
            rate = rates.get(code)
            ws.append(
                [
                    rate.code,
                    rate.description,
                    rate.unit or "",
                    rate.supplier or "",
                    rate.quoted_on or "",
                    rate.source_note or "",
                ]
            )

    for col, width in (("A", 26), ("B", 42), ("C", 8), ("D", 22), ("E", 14), ("F", 50)):
        ws.column_dimensions[col].width = width


# -- helpers ------------------------------------------------------------------------


def _wastage_for(item: QuantityItem, factors: Factors) -> float:
    from boq.rules.factors import _WASTAGE_BY_TRADE

    key = _WASTAGE_BY_TRADE.get(item.trade or "")
    return factors.wastage(key) if key else 0.0


def _source_label(item: QuantityItem) -> str:
    src = item.source
    parts = [src.file]
    if src.sheet:
        parts.append(src.sheet)
    if src.page:
        parts.append(f"p{src.page}")
    if src.cell:
        parts.append(src.cell)
    return " / ".join(parts)


def _notes(item: QuantityItem, rated) -> str:
    bits: list[str] = []
    if rated.unit_mismatch and rated.rate:
        bits.append(
            f"unit mismatch: item is {item.unit}, rate {rated.rate.code} is {rated.rate.unit}"
        )
    if item.flags:
        bits.append("flags: " + ", ".join(item.flags))
    if item.notes:
        bits.append(item.notes)
    return " | ".join(bits)
