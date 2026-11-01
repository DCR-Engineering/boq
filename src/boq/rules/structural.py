"""Structural derived quantities.

On DCR2564 almost nothing here can be computed, and saying so precisely is the deliverable.
Guardrail 1: missing is ``null`` plus a reason, never a quiet estimate.

Three distinct reasons quantities are unavailable, and the distinction matters to the
engineer reading the BoQ:

* **not issued** -- the design exists but was delegated. Suspended slabs are marked
  "POST-TENSION SLAB -- BY PT SPECIALIST" on every framing sheet.
* **needs plan geometry** -- the schedule gives a section but not a length. The footing
  schedule states ``L = SEE PLAN``; the beam schedule gives no sizes at all.
* **extractor not built** -- the schedule exists and is readable, but its parser is blocked.

Only the third is a limitation of this tool. The first two are properties of the documents.
"""

from __future__ import annotations

from boq.normalize.items import QuantityItem, Source

STRUCTURAL_FILE = "STR2564.pdf"

# Reason codes, so the review UI can group and the BoQ can explain.
NOT_ISSUED = "not-issued"
NEEDS_GEOMETRY = "needs-plan-geometry"
EXTRACTOR_BLOCKED = "extractor-not-built"


def _src(page: int, sheet: str, region: str) -> Source:
    # bbox is required for a pdf source; a whole-sheet box is honest when the region has not
    # been located to a tighter box yet.
    return Source(
        file=STRUCTURAL_FILE,
        file_type="pdf",
        page=page,
        sheet=sheet,
        region=region,
        bbox=(0.0, 0.0, 1684.0, 1191.0),
    )


def _unavailable(
    item_id: str,
    element: str,
    unit: str,
    reason: str,
    code: str,
    page: int,
    sheet: str,
    region: str,
    *,
    level: str | None = None,
    trade: str = "superstructure_concrete",
    spec: dict | None = None,
) -> QuantityItem:
    return QuantityItem(
        id=item_id,
        discipline="structural",
        trade=trade,
        element=element,
        level=level,
        quantity=None,
        unit=unit,
        method="unavailable",
        null_reason=reason,
        source=_src(page, sheet, region),
        confidence=1.0,
        spec=spec or {},
        flags=[code],
    )


def post_tension_slabs() -> list[QuantityItem]:
    """PT slabs are by specialist: no thickness, tendon count, strand length or anchorages."""
    out: list[QuantityItem] = []
    reason = (
        "suspended slabs are marked 'POST-TENSION SLAB - BY PT SPECIALIST' and the sheets "
        "carry 'DESIGN MUST BE REVIEW AFTER PT DESIGN'; no thickness or tendon data is "
        "issued. The thermal workbook's 200mm slab figure is that document's own assumption "
        "and must not be promoted into a structural quantity."
    )
    for level, page, sheet in (
        ("first", 6, "ST - 03"),
        ("second", 7, "ST - 04"),
        ("roof", 8, "ST - 05"),
    ):
        out.append(
            _unavailable(
                f"conc.slab.pt.{level}",
                "post-tensioned slab",
                "m3",
                reason,
                NOT_ISSUED,
                page,
                sheet,
                "framing plan note",
                level=level,
            )
        )
    out.append(
        _unavailable(
            "pt.tendon.strand",
            "PT tendon strand",
            "m",
            reason,
            NOT_ISSUED,
            13,
            "ST - 09",
            "PT general notes",
            trade="superstructure_concrete",
        )
    )
    out.append(
        _unavailable(
            "pt.anchorage.count",
            "PT anchorage",
            "nr",
            reason,
            NOT_ISSUED,
            14,
            "ST - 10",
            "PT anchorage details",
        )
    )
    return out


def geometry_dependent() -> list[QuantityItem]:
    """Quantities whose sections are scheduled but whose lengths live only on the plans."""
    return [
        _unavailable(
            "conc.footing.strip",
            "strip footing",
            "m3",
            "the footing schedule gives B and D but states 'L = SEE PLAN'; run lengths must "
            "come from plan geometry (DWF or a vision pass), which is not yet implemented",
            NEEDS_GEOMETRY,
            5,
            "ST - 02",
            "footing schedule",
            level="foundation",
            trade="substructure",
            spec={"marks": ["SF1", "SF2", "SF3", "SF4"], "depth_mm": 400},
        ),
        _unavailable(
            "conc.beam.suspended",
            "reinforced concrete beam",
            "m3",
            "the beam schedule gives reinforcement only; B1/B2/B3 sizes are annotated on the "
            "framing plans and extra bars are 'shown in plan', so neither section nor length "
            "is available from the schedule",
            NEEDS_GEOMETRY,
            6,
            "ST - 03",
            "schedule of beams",
            spec={"marks": ["B1", "B2", "B3"]},
        ),
        _unavailable(
            "conc.slab.ground",
            "ground slab",
            "m3",
            "GS-1 (100mm, BRC A142) and GS-2 (300mm, Y16@200 T&B) are specified but their "
            "areas are not scheduled; slab extents must come from plan geometry",
            NEEDS_GEOMETRY,
            5,
            "ST - 02",
            "ground slab schedule",
            level="ground",
            trade="substructure",
            spec={"GS-1": "100mm solid, BRC A142", "GS-2": "300mm solid, Y16@200 T&B"},
        ),
    ]


def extractor_blocked() -> list[QuantityItem]:
    """Quantities a built extractor would produce, from schedules that are readable today."""
    reason_tpl = (
        "the {what} is present and machine-readable on {sheet}, but its extractor is not "
        "built: the sample drawings were unavailable when it was due, and a positional "
        "parser cannot be written or tested without the real per-word coordinates"
    )
    return [
        _unavailable(
            "conc.column.volume",
            "reinforced concrete column",
            "m3",
            reason_tpl.format(what="column schedule", sheet="ST - 02"),
            EXTRACTOR_BLOCKED,
            5,
            "ST - 02",
            "column schedule",
            spec={"marks": ["C1", "C2", "C3", "C4", "BC"]},
        ),
        _unavailable(
            "conc.groundbeam.volume",
            "ground beam",
            "m3",
            reason_tpl.format(what="ground beam schedule", sheet="ST - 02"),
            EXTRACTOR_BLOCKED,
            5,
            "ST - 02",
            "ground beam schedule",
            level="foundation",
            trade="substructure",
            spec={"marks": ["GB-1", "GB-2", "GB-3", "GB-4"]},
        ),
        _unavailable(
            "steel.reinforcement.total",
            "reinforcement steel",
            "kg",
            "Set B contains no bar bending schedule, so steel must be derived from schedule "
            "callouts; those schedules' extractors are not built yet, and any derived figure "
            "must be flagged 'derived' when it is",
            EXTRACTOR_BLOCKED,
            5,
            "ST - 02",
            "column and footing schedules",
            trade="reinforcement",
        ),
        _unavailable(
            "formwork.total",
            "formwork / shuttering",
            "m2",
            "formwork is contact area, so it depends on the concrete element geometry that is "
            "not yet available",
            EXTRACTOR_BLOCKED,
            5,
            "ST - 02",
            "schedules",
        ),
    ]


def ratios(built_up_area_m2: float | None) -> list[QuantityItem]:
    """Benchmark ratios. Both numerators are unavailable, so both ratios are null.

    The built-up area denominator *is* known, which is worth recording: the moment the
    concrete extractors land, these compute with no further input.
    """
    return [
        QuantityItem(
            id="ratio.steel_per_concrete",
            discipline="structural",
            trade="reinforcement",
            element="reinforcement per concrete volume",
            quantity=None,
            unit="kg",
            method="unavailable",
            null_reason=(
                "needs total reinforcement mass and total concrete volume; both are "
                "unavailable (see steel.reinforcement.total and the concrete items)"
            ),
            source=_src(5, "ST - 02", "schedules"),
            confidence=1.0,
            derived_from=["steel.reinforcement.total"],
            spec={"unit_description": "kg steel per m3 concrete"},
        ),
        QuantityItem(
            id="ratio.concrete_per_builtup",
            discipline="structural",
            trade="superstructure_concrete",
            element="concrete volume per built-up area",
            quantity=None,
            unit="m3",
            method="unavailable",
            null_reason=(
                "the built-up area denominator is known"
                + (f" ({built_up_area_m2} m2)" if built_up_area_m2 else "")
                + ", but total concrete volume is unavailable"
            ),
            source=_src(5, "ST - 02", "schedules"),
            confidence=1.0,
            spec={
                "unit_description": "m3 concrete per m2 built-up area",
                "denominator_m2": built_up_area_m2,
            },
        ),
    ]


def all_items(built_up_area_m2: float | None = None) -> list[QuantityItem]:
    return [
        *post_tension_slabs(),
        *geometry_dependent(),
        *extractor_blocked(),
        *ratios(built_up_area_m2),
    ]
