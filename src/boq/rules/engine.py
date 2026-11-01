"""The derived quantities engine.

Takes Phase 2 extractor output and produces a complete, schema-valid project quantities
document: every quantity the documents support, and an explicit null-with-reason for every
one they do not.

All arithmetic is plain Python. No model call computes a total (guardrail 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from boq.crosscheck import checks
from boq.normalize.items import QuantityItem, Source, build_document, validate
from boq.rules import envelope, structural
from boq.rules.factors import Factors, PricedQuantity, apply_all, default_factors


@dataclass
class EngineResult:
    items: list[QuantityItem]
    cross_checks: list[checks.CheckResult]
    document: dict[str, Any]

    # -- summaries the review screen and the analysis report need ------------------

    @property
    def available(self) -> list[QuantityItem]:
        return [i for i in self.items if i.is_available]

    @property
    def unavailable(self) -> list[QuantityItem]:
        return [i for i in self.items if not i.is_available]

    @property
    def blocking(self) -> list[checks.CheckResult]:
        return checks.blocking_failures(self.cross_checks)

    @property
    def exportable(self) -> bool:
        """Nothing exports while a blocking check is unresolved (build prompt section 7)."""
        return not self.blocking

    def by_trade(self) -> dict[str, list[QuantityItem]]:
        out: dict[str, list[QuantityItem]] = {}
        for item in self.items:
            out.setdefault(item.trade or "unclassified", []).append(item)
        return out

    def priced(self, factors: Factors | None = None) -> list[PricedQuantity]:
        """Reporting views with wastage applied -- never stored back onto the items."""
        return apply_all(self.items, factors or default_factors())

    def coverage(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.method] = counts.get(item.method, 0) + 1
        return counts


def run(
    *,
    area_schedule=None,
    thermal=None,
    set_a_window_counts: dict[str, int] | None = None,
    project_identifiers: dict[str, str] | None = None,
    project: dict[str, Any] | None = None,
    source_files: list[dict[str, Any]] | None = None,
    factors: Factors | None = None,
    thermal_file: str = envelope.THERMAL_FILE,
) -> EngineResult:
    """Derive every quantity the available extractor output supports."""
    factors = factors or default_factors()
    items: list[QuantityItem] = []

    if area_schedule is not None:
        items.extend(_area_items(area_schedule))

    if thermal is not None:
        items.extend(envelope.blockwork(thermal, factors, file=thermal_file))
        items.extend(envelope.plaster_and_paint(thermal, file=thermal_file))
        items.extend(envelope.insulation(thermal, file=thermal_file))
        items.extend(envelope.glazing(thermal, file=thermal_file))

    built_up = getattr(area_schedule, "total_built_up", None)
    items.extend(structural.all_items(built_up))

    results = checks.run_all(
        area_schedule=area_schedule,
        thermal=thermal,
        set_a_window_counts=set_a_window_counts,
        project_identifiers=project_identifiers,
    )
    results.append(_check_envelope_decomposition(thermal))

    document = build_document(
        project=project or {"project_no": "UNKNOWN", "title": "UNKNOWN"},
        items=items,
        source_files=source_files or [],
        factors_version=factors.version,
        cross_checks=results,
    )

    errors = validate(document)
    if errors:
        raise ValueError(
            "engine produced a document that violates the v1 schema:\n  " + "\n  ".join(errors)
        )

    return EngineResult(items=items, cross_checks=results, document=document)


# -- area items ----------------------------------------------------------------------


_AREA_SOURCE = Source(
    file="DCR2564_FINAL_DRAWINGS.pdf",
    file_type="pdf",
    page=5,
    sheet="N04",
    region="schedule of built-up areas",
    bbox=(190.0, 70.0, 610.0, 460.0),
)


def _area_items(schedule) -> list[QuantityItem]:
    items: list[QuantityItem] = []

    if schedule.plot_area is not None:
        items.append(
            QuantityItem(
                id="area.plot",
                discipline="architectural",
                trade=None,
                element="plot (land) area",
                quantity=schedule.plot_area,
                unit="m2",
                method="extracted",
                source=_AREA_SOURCE,
                confidence=0.98,
            )
        )

    for floor in schedule.floors:
        key = floor.name.lower().replace(" ", "_")
        if floor.built_up is not None:
            items.append(
                QuantityItem(
                    id=f"area.builtup.{key}",
                    discipline="architectural",
                    trade=None,
                    element="built-up area",
                    level=floor.name,
                    quantity=floor.built_up,
                    unit="m2",
                    method="extracted",
                    source=_AREA_SOURCE,
                    confidence=0.98,
                    spec={"details": floor.details},
                )
            )

    if schedule.total_built_up is not None:
        items.append(
            QuantityItem(
                id="area.builtup.total",
                discipline="architectural",
                trade=None,
                element="total built-up area",
                quantity=schedule.total_built_up,
                unit="m2",
                method="extracted",
                source=_AREA_SOURCE,
                confidence=0.98,
                cross_checks=["area_schedule_internal"],
            )
        )

    return items


# -- the envelope decomposition check ---------------------------------------------------


def _check_envelope_decomposition(calc, tol: float = 0.01) -> checks.CheckResult:
    """glass + opaque wall + columns + beams should equal the total envelope surface.

    This is what establishes that the stated wall area is already net of openings, columns
    and beams. Without it, deducting openings again would understate blockwork by about 28 %
    on this project.
    """
    if calc is None or calc.declared_surface_area_m2 is None:
        return checks.CheckResult(
            "envelope_decomposition",
            "Envelope decomposition: glass + wall + columns + beams = total surface",
            "not_applicable",
        )

    parts = {
        "glass": calc.computed_glass_area_m2,
        "wall": _area(calc, "external_walls"),
        "columns": _area(calc, "external_columns"),
        "beams": _area(calc, "external_beams"),
    }
    if any(v is None for v in parts.values()):
        missing = [k for k, v in parts.items() if v is None]
        return checks.CheckResult(
            "envelope_decomposition",
            "Envelope decomposition",
            "not_possible",
            detail=f"missing component areas: {', '.join(missing)}",
        )

    total = sum(parts.values())
    declared = calc.declared_surface_area_m2
    agree = abs(total - declared) <= tol

    return checks.CheckResult(
        check_id="envelope_decomposition",
        description="Envelope decomposition: glass + wall + columns + beams = total surface",
        status="pass" if agree else "fail",
        left=round(declared, 3),
        right=round(total, 3),
        tolerance=tol,
        detail=(
            " + ".join(f"{k} {v:.3f}" for k, v in parts.items())
            + f" = {total:.3f} m2 against a declared {declared:.3f} m2"
            + (
                ". Confirms the stated wall area is already net of openings, columns and beams."
                if agree
                else ". The components do not account for the declared total."
            )
        ),
        blocking=not agree,
    )


def _area(calc, element: str) -> float | None:
    el = calc.envelope.get(element)
    return None if el is None else el.area_m2
