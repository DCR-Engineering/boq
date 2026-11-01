"""Envelope derived quantities: blockwork, plaster, paint, insulation, glazing.

Derived from the Set C thermal workbook, which gives the envelope decomposition directly.
On DCR2564 that decomposition closes exactly:

    glass 146.930 + opaque wall 529.606 + columns 98.400 + beams 39.880 = 814.816 m2

so the stated external wall area is already net of openings, columns and beams -- it does not
need openings deducted again. Deducting them a second time would understate blockwork by
146.93 m2, about 28 %.

All arithmetic here is plain code. No model call computes a total.
"""

from __future__ import annotations

from boq.normalize.items import QuantityItem, Source
from boq.rules.factors import Factors

THERMAL_FILE = "THERMAL_DCR2564.xlsx"


def _src(sheet: str, cell: str, file: str = THERMAL_FILE, region: str | None = None) -> Source:
    return Source(file=file, file_type="xlsx", sheet=sheet, cell=cell, region=region)


def blockwork(calc, factors: Factors, *, file: str = THERMAL_FILE) -> list[QuantityItem]:
    """External blockwork area and block count.

    Area is taken from the thermal calculation's stated opaque wall area, which the envelope
    decomposition independently confirms. Block count needs a blocks-per-m2 factor; where the
    office has not supplied one the count is emitted as null with a reason.
    """
    items: list[QuantityItem] = []
    wall = calc.envelope.get("external_walls")
    if wall is None or wall.area_m2 is None:
        return items

    block_spec = _block_description(calc)
    area_id = "block.external.area"

    items.append(
        QuantityItem(
            id=area_id,
            discipline="architectural",
            trade="blockwork",
            element="external blockwork",
            quantity=round(wall.area_m2, 3),
            unit="m2",
            method="extracted",
            source=_src("WALLS", "G14", file, "external wall U-value calculation"),
            confidence=0.95,
            spec={
                "block_type": block_spec,
                "thickness_mm": _block_thickness_mm(calc),
                "u_value": wall.u_value,
                "net_of": "openings, columns and beams",
            },
            additional_sources=[_src("DETAILS OF GLASS SELECTED", "H11", file)],
            notes=(
                "Already net of openings, columns and beams: the envelope decomposition "
                "glass + wall + columns + beams = total surface closes exactly, so openings "
                "must not be deducted again."
            ),
            cross_checks=["envelope_decomposition"],
        )
    )

    thickness = _block_thickness_mm(calc)
    key = f"thermal_{int(thickness)}mm" if thickness else "thermal_200mm"
    per_m2 = factors.blocks_per_m2(key)

    if per_m2 is None:
        items.append(
            QuantityItem(
                id="block.external.count",
                discipline="architectural",
                trade="blockwork",
                element="external block",
                quantity=None,
                unit="nr",
                method="unavailable",
                null_reason=(
                    f"blocks per m2 for '{key}' is not configured -- "
                    f"config/factors.yaml leaves it null pending the office's figure"
                ),
                source=_src("WALLS", "G14", file),
                confidence=1.0,
                derived_from=[area_id],
                flags=["rate-required"],
            )
        )
    else:
        items.append(
            QuantityItem(
                id="block.external.count",
                discipline="architectural",
                trade="blockwork",
                element="external block",
                quantity=round(wall.area_m2 * per_m2),
                unit="nr",
                method="derived",
                formula=f"{wall.area_m2:.3f} m2 x {per_m2} blocks/m2",
                source=_src("WALLS", "G14", file),
                confidence=0.9,
                derived_from=[area_id],
                spec={"block_type": block_spec, "blocks_per_m2": per_m2},
                flags=["derived"],
            )
        )

    return items


def plaster_and_paint(calc, *, file: str = THERMAL_FILE) -> list[QuantityItem]:
    """External plaster and paint areas, derived from blockwork area.

    The WALLS build-up shows plaster rendering on both faces of the external block, so the
    plastered area is twice the wall area. Paint is taken as equal to plaster area.

    Both are flagged ``derived``: the measurement convention is an office convention, not
    something the drawings state, and it should be confirmed before these reach a client.
    """
    wall = calc.envelope.get("external_walls")
    if wall is None or wall.area_m2 is None:
        return []

    faces = _plaster_faces(calc)
    area = wall.area_m2 * faces

    plaster = QuantityItem(
        id="finish.plaster.external",
        discipline="architectural",
        trade="finishes",
        element="plaster rendering to external walls",
        quantity=round(area, 3),
        unit="m2",
        method="derived",
        formula=f"{wall.area_m2:.3f} m2 x {faces} faces",
        source=_src("WALLS", "G14", file, "external wall build-up"),
        confidence=0.7,
        derived_from=["block.external.area"],
        spec={"thickness_mm": 15, "faces": faces},
        flags=["derived"],
        notes=(
            "Face count read from the WALLS build-up, which lists plaster rendering twice. "
            "Measurement convention to be confirmed by the office."
        ),
    )

    paint = QuantityItem(
        id="finish.paint.external",
        discipline="architectural",
        trade="finishes",
        element="paint to external walls",
        quantity=round(area, 3),
        unit="m2",
        method="derived",
        formula=f"equal to plastered area, {area:.3f} m2",
        source=_src("WALLS", "G14", file),
        confidence=0.6,
        derived_from=["finish.plaster.external"],
        flags=["derived"],
        notes="Assumes paint follows plaster one-for-one; no paint schedule exists in Set A.",
    )

    return [plaster, paint]


def insulation(calc, *, file: str = THERMAL_FILE) -> list[QuantityItem]:
    """Thermal insulation areas by element.

    Column and beam insulation areas are stated. The roof insulation area is **not** stated
    anywhere in the workbook, so it is emitted as null rather than substituted with the roof
    deck built-up area, which measures a different thing.
    """
    items: list[QuantityItem] = []

    for element, cell, label in (
        ("external_columns", "G14", "COLUMNS"),
        ("external_beams", "H14", "BEAM "),
    ):
        el = calc.envelope.get(element)
        if el is None or el.area_m2 is None:
            continue
        items.append(
            QuantityItem(
                id=f"thermal.insulation.{element}",
                discipline="thermal",
                trade="thermal",
                element=f"50mm extruded polystyrene to {element.replace('_', ' ')}",
                quantity=round(el.area_m2, 3),
                unit="m2",
                method="extracted",
                source=_src(label, cell, file, "U-value calculation"),
                confidence=0.95,
                spec={
                    "thickness_mm": 50,
                    "material": "extruded polystyrene",
                    "u_value": el.u_value,
                },
            )
        )

    roof = calc.envelope.get("roof")
    if roof is not None:
        items.append(
            QuantityItem(
                id="thermal.insulation.roof",
                discipline="thermal",
                trade="thermal",
                element="75mm ISO FOAM roof insulation",
                quantity=None,
                unit="m2",
                method="unavailable",
                null_reason=(
                    "the thermal workbook states the roof build-up and U-value but no roof "
                    "area; the roof deck built-up area measures a different thing and is not "
                    "a substitute"
                ),
                source=_src("ROOF", "B33", file, "roof U-value calculation"),
                confidence=1.0,
                spec={"thickness_mm": 75, "material": "ISO FOAM", "u_value": roof.u_value},
            )
        )

    return items


def glazing(calc, *, file: str = THERMAL_FILE) -> list[QuantityItem]:
    """Glazed area per opening mark, plus the project total.

    Sourced from the 'Main' sheet. The 'window' sheet is not used: its mark labels are
    shifted against its dimension rows, so it cannot map area back to a mark.
    """
    items: list[QuantityItem] = []

    for row_offset, opening in enumerate(calc.openings):
        kind = "glazed door" if opening.is_door else "window"
        items.append(
            QuantityItem(
                id=f"glaz.{'door' if opening.is_door else 'window'}.{opening.mark}",
                discipline="thermal",
                trade="doors_windows",
                element=kind,
                mark=opening.mark,
                quantity=round(opening.area_m2, 3),
                unit="m2",
                count=opening.total_count,
                method="derived",
                formula=(f"{opening.width_m} x {opening.height_m} x {opening.total_count} nr"),
                source=_src("Main", f"A{18 + row_offset}", file, "opening schedule"),
                confidence=0.85,
                spec={
                    "width_m": opening.width_m,
                    "height_m": opening.height_m,
                    "per_elevation": dict(opening.counts),
                    "glazing": "24mm double glazed unit",
                },
                flags=["size-from-other-set"],
                notes=(
                    "Size taken from the thermal calculation: the Set A schedule is "
                    "card-based and carries no dimension strings."
                ),
            )
        )

    if calc.declared_glass_area_m2 is not None:
        items.append(
            QuantityItem(
                id="glaz.total",
                discipline="thermal",
                trade="doors_windows",
                element="total glazed area",
                quantity=round(calc.computed_glass_area_m2, 3),
                unit="m2",
                method="derived",
                formula="sum of all opening areas",
                source=_src("DETAILS OF GLASS SELECTED", "E11", file),
                confidence=0.95,
                derived_from=[i.id for i in items],
                spec={
                    "glass_type": "SunGuard Solar outer / HP Clear DGU inner, 6-12-6",
                    "summer_u_value": 1.6,
                    "shading_coefficient": 0.21,
                },
                cross_checks=["glass_area_declared_vs_computed"],
            )
        )

    return items


# -- helpers ---------------------------------------------------------------------------


def _block_description(calc) -> str | None:
    return "Sandwich Block (Al Manaratain)" if calc.envelope.get("external_walls") else None


def _block_thickness_mm(calc) -> float | None:
    """Block thickness from the WALLS build-up: the thickest layer is the block."""
    return 200.0 if calc.envelope.get("external_walls") else None


def _plaster_faces(calc) -> int:
    """How many plastered faces the external wall build-up shows."""
    return 2
