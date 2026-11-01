"""Consistency checks between document sets.

The cross-check panel from section 7 of the build prompt. These are pure functions over
extractor output, so they run headless in CI as well as in the review UI.

Results use the vocabulary of ``schema/project_quantities.v1.json``:

    pass          the two sources agree
    fail          they disagree and the difference is not explained
    reconciled    they differ, but the difference is fully accounted for
    not_possible  the comparison cannot be made from the issued documents
    not_applicable the inputs do not exist for this project

A lesson from DCR2564 is baked in here: **compare item by item, not by total**. Set A and
Set C disagree on six window marks, yet their totals differ by only two, because the
discrepancies partly cancel. A totals-only check reports that as reconciled and misses it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# "W01" -> "W1", "SD01" -> "SD1": the two sets pad mark numbers differently.
_PAD = re.compile(r"^([A-Za-z]+)0*(\d+)")
# "W8A"/"W8B" -> "W8": Set C splits some marks into leaves that Set A keeps whole.
_LEAF = re.compile(r"^([A-Za-z]+\d+)[A-Za-z]$")


def normalise_mark(mark: str) -> str:
    """Canonical form of a schedule mark, for comparison across document sets."""
    m = _PAD.sub(lambda g: f"{g.group(1).upper()}{int(g.group(2))}", mark.strip().upper())
    return _LEAF.sub(r"\1", m)


@dataclass
class CheckResult:
    check_id: str
    description: str
    status: str
    left: float | str | None = None
    right: float | str | None = None
    tolerance: float | None = None
    deviation_pct: float | None = None
    detail: str = ""
    blocking: bool = False
    item_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status in ("pass", "reconciled", "not_applicable")

    def __str__(self) -> str:
        return f"{self.status.upper():14s} {self.check_id}: {self.detail or self.description}"


def _deviation(left: float, right: float) -> float | None:
    return None if left == 0 else abs(right - left) / abs(left) * 100


# -- individual checks ------------------------------------------------------------------


def check_area_schedule_internal(schedule) -> CheckResult:
    """The area table's own arithmetic identities (docs section 5.1)."""
    if schedule is None:
        return CheckResult(
            "area_schedule_internal",
            "Area schedule internal arithmetic",
            "not_applicable",
            detail="no area schedule extracted",
        )
    problems = schedule.check()
    return CheckResult(
        check_id="area_schedule_internal",
        description="Area schedule internal arithmetic",
        status="pass" if not problems else "fail",
        detail="all identities hold" if not problems else "; ".join(problems),
        blocking=bool(problems),
    )


def check_glass_area(calc, tol: float = 0.01) -> CheckResult:
    """Declared glazed area vs the sum of the workbook's own openings."""
    if calc is None or calc.declared_glass_area_m2 is None or not calc.openings:
        return CheckResult(
            "glass_area_declared_vs_computed",
            "Glazed area: declared vs recomputed",
            "not_applicable",
        )
    left = calc.declared_glass_area_m2
    right = calc.computed_glass_area_m2
    agree = abs(right - left) <= tol
    return CheckResult(
        check_id="glass_area_declared_vs_computed",
        description="Glazed area: declared vs recomputed from opening sizes",
        status="pass" if agree else "fail",
        left=round(left, 3),
        right=round(right, 3),
        tolerance=tol,
        deviation_pct=_deviation(left, right),
        detail=(
            f"{left:.3f} m2 declared, {right:.3f} m2 recomputed"
            + ("" if agree else " -- the declared total is not supported by its own inputs")
        ),
        blocking=not agree,
    )


def check_wall_area(calc, tol: float = 0.01) -> CheckResult:
    """Declared envelope surface area vs the per-elevation wall areas."""
    if calc is None or calc.declared_surface_area_m2 is None or not calc.wall_areas:
        return CheckResult(
            "wall_area_declared_vs_computed",
            "Envelope wall area: declared vs recomputed",
            "not_applicable",
        )
    left = calc.declared_surface_area_m2
    right = calc.computed_wall_area_m2
    agree = abs(right - left) <= tol
    return CheckResult(
        check_id="wall_area_declared_vs_computed",
        description="Envelope wall area: declared vs sum of elevations",
        status="pass" if agree else "fail",
        left=round(left, 3),
        right=round(right, 3),
        tolerance=tol,
        deviation_pct=_deviation(left, right),
        detail=f"{left:.3f} m2 declared, {right:.3f} m2 from the elevation table",
        blocking=not agree,
    )


def check_window_counts(set_a_counts: dict[str, int] | None, calc) -> CheckResult:
    """Window quantities, Set A schedule vs Set C calculation, **compared per mark**.

    ``set_a_counts`` maps mark -> quantity from the Set A window schedule.

    Marks are normalised so W01 matches W1, and Set C's split leaves (W8A + W8B) are folded
    back onto their base mark before comparison.
    """
    if not set_a_counts or calc is None or not calc.openings:
        return CheckResult(
            "window_count_setA_vs_setC",
            "Window quantities: Set A vs Set C",
            "not_possible",
            detail="one of the two schedules is unavailable",
        )

    left = {normalise_mark(m): q for m, q in set_a_counts.items()}
    right: dict[str, int] = {}
    for o in calc.openings:
        if o.is_door:
            continue
        key = normalise_mark(o.mark)
        right[key] = right.get(key, 0) + o.total_count

    mismatches = [
        f"{m}: Set A {left.get(m, 0)} vs Set C {right.get(m, 0)}"
        for m in sorted(set(left) | set(right), key=_mark_sort_key)
        if left.get(m, 0) != right.get(m, 0)
    ]
    total_left, total_right = sum(left.values()), sum(right.values())

    if not mismatches:
        return CheckResult(
            check_id="window_count_setA_vs_setC",
            description="Window quantities: Set A vs Set C, per mark",
            status="pass",
            left=total_left,
            right=total_right,
            detail=f"all {len(left)} marks agree ({total_left} units)",
        )

    return CheckResult(
        check_id="window_count_setA_vs_setC",
        description="Window quantities: Set A vs Set C, per mark",
        status="fail",
        left=total_left,
        right=total_right,
        deviation_pct=_deviation(total_left, total_right),
        detail=(
            f"{len(mismatches)} of {len(set(left) | set(right))} marks disagree "
            f"({'; '.join(mismatches)}). Totals differ by only "
            f"{total_right - total_left:+d} because the discrepancies partly cancel, so a "
            f"totals-only comparison would wrongly report agreement."
        ),
        blocking=True,
    )


def check_project_identifiers(identifiers: dict[str, str]) -> CheckResult:
    """Every rendering of the project number across the document sets should agree.

    ``identifiers`` maps a source label to the identifier found there.
    """
    if not identifiers:
        return CheckResult(
            "project_id_consistency", "Project identifier consistency", "not_applicable"
        )

    normalised = {re.sub(r"[^0-9]", "", v): v for v in identifiers.values() if v}
    digits = {re.sub(r"^0+", "", d) for d in normalised if d}
    if len(digits) <= 1:
        return CheckResult(
            check_id="project_id_consistency",
            description="Project identifier consistency",
            status="pass",
            detail=f"all sources agree: {sorted(set(identifiers.values()))}",
        )

    listing = ", ".join(f"{src} = {val!r}" for src, val in sorted(identifiers.items()))
    return CheckResult(
        check_id="project_id_consistency",
        description="Project identifier consistency",
        status="fail",
        detail=f"{len(digits)} different project numbers across the sets: {listing}",
    )


def check_spreadsheet_errors(calc) -> CheckResult:
    """Any live error cell in the thermal workbook blocks export."""
    if calc is None:
        return CheckResult(
            "thermal_spreadsheet_errors", "Thermal workbook error cells", "not_applicable"
        )
    if not calc.error_cells:
        return CheckResult(
            check_id="thermal_spreadsheet_errors",
            description="Thermal workbook error cells",
            status="pass",
            detail="no error cells",
        )
    return CheckResult(
        check_id="thermal_spreadsheet_errors",
        description="Thermal workbook error cells",
        status="fail",
        left=len(calc.error_cells),
        detail=(
            f"{len(calc.error_cells)} error cells: "
            f"{', '.join(str(e) for e in calc.error_cells)}. "
            "The values they feed are unknown and must not be read as zero."
        ),
        blocking=True,
    )


def check_slab_spec(structural_slab: str | None, calc) -> CheckResult:
    """Slab specification, structural set vs thermal assumption.

    On DCR2564 the structural set defers suspended slabs to a PT specialist while the thermal
    workbook assumes a 150 mm precast slab and a 200 mm slab thickness. Those are assumptions
    of a different document and must never be promoted into a structural quantity.
    """
    thermal_slab = calc.envelope.get("roof") if calc else None
    if structural_slab is None:
        return CheckResult(
            check_id="slab_spec_structural_vs_thermal",
            description="Slab specification: structural vs thermal",
            status="not_possible",
            right="150mm precast (thermal assumption)" if thermal_slab else None,
            detail=(
                "the structural set issues no suspended-slab thickness -- PT design is by "
                "specialist. The thermal workbook's slab build-up is its own assumption and "
                "is not a substitute."
            ),
            blocking=True,
        )
    return CheckResult(
        check_id="slab_spec_structural_vs_thermal",
        description="Slab specification: structural vs thermal",
        status="pass",
        left=structural_slab,
    )


def _mark_sort_key(mark: str) -> tuple[str, int]:
    m = re.match(r"^([A-Za-z]+)(\d+)$", mark)
    return (m.group(1), int(m.group(2))) if m else (mark, 0)


# -- runner -------------------------------------------------------------------------------


def run_all(
    *,
    area_schedule=None,
    thermal=None,
    set_a_window_counts: dict[str, int] | None = None,
    project_identifiers: dict[str, str] | None = None,
    structural_slab_spec: str | None = None,
) -> list[CheckResult]:
    """Run every check for which inputs are available.

    Checks whose inputs are missing report ``not_applicable`` or ``not_possible`` rather than
    being silently skipped -- an absent check must be visible in the review panel.
    """
    return [
        check_area_schedule_internal(area_schedule),
        check_glass_area(thermal),
        check_wall_area(thermal),
        check_window_counts(set_a_window_counts, thermal),
        check_spreadsheet_errors(thermal),
        check_slab_spec(structural_slab_spec, thermal),
        check_project_identifiers(project_identifiers or {}),
    ]


def blocking_failures(results: list[CheckResult]) -> list[CheckResult]:
    """Results that must be resolved before anything is exported (build prompt section 7)."""
    return [r for r in results if r.blocking and r.status == "fail"] + [
        r for r in results if r.blocking and r.status == "not_possible"
    ]
