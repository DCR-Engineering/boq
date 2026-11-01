"""Derived quantities engine tests, on the real DCR2564 sample."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.normalize.items import QuantityItem, Source, validate
from boq.rules import engine, structural
from boq.rules.factors import Factors, apply_wastage
from boq.text.words import load_words

FIXTURES = Path(__file__).parent / "fixtures" / "DCR2564"

SET_A_WINDOWS = {
    "W01": 2,
    "W02": 3,
    "W03": 2,
    "W05": 1,
    "W06": 2,
    "W07": 1,
    "W08": 1,
    "W09": 1,
    "W10": 2,
    "W13": 1,
    "W14": 1,
    "W15": 1,
    "W16": 2,
    "W17": 2,
}


@pytest.fixture(scope="module")
def thermal():
    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text(encoding="utf-8"))
    return thermal_calc.parse(CellMap.from_dict(payload["sheets"]))


@pytest.fixture(scope="module")
def areas():
    return area_schedule.parse(load_words(FIXTURES / "arch_p05_area_schedule.words.json"))


@pytest.fixture(scope="module")
def result(areas, thermal):
    return engine.run(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project_identifiers={"Set A": "DCR2564", "Set C": "DCR2503"},
        project={"project_no": "DCR2564", "title": "Proposed Two Storey Villa"},
        source_files=[
            {"file": "THERMAL_DCR2564.xlsx", "sha256": "b" * 64, "set": "C", "file_type": "xlsx"}
        ],
    )


def _item(result, item_id: str) -> QuantityItem:
    return next(i for i in result.items if i.id == item_id)


# -- schema conformance -----------------------------------------------------------------


def test_document_is_schema_valid(result):
    assert validate(result.document) == []


def test_engine_refuses_to_emit_an_invalid_document(areas, thermal, monkeypatch):
    """Guardrail: a malformed item must fail loudly, not slip into the output."""

    def bad(*_args, **_kwargs):
        return [
            QuantityItem(
                id="bad.item",
                discipline="structural",
                element="x",
                quantity=1.0,
                unit="m2",
                method="extracted",
                source=Source(file="f.pdf"),
                confidence=0.5,
                flags=["not-a-real-flag"],
            )
        ]

    monkeypatch.setattr(structural, "all_items", bad)
    with pytest.raises(ValueError, match="violates the v1 schema"):
        engine.run(area_schedule=areas, thermal=thermal)


# -- envelope decomposition --------------------------------------------------------------


def test_envelope_decomposition_passes(result):
    check = next(c for c in result.cross_checks if c.check_id == "envelope_decomposition")
    assert check.status == "pass"
    assert check.left == pytest.approx(814.816)
    assert check.right == pytest.approx(814.816)


def test_blockwork_area_is_not_double_deducted(result):
    """The stated wall area is already net; deducting openings again loses 146.93 m2."""
    block = _item(result, "block.external.area")
    assert block.quantity == pytest.approx(529.606)
    assert block.quantity != pytest.approx(529.606 - 146.93)


# -- blockwork and the missing factor -------------------------------------------------------


def test_block_count_is_null_with_a_reason_not_a_guess(result):
    count = _item(result, "block.external.count")
    assert count.quantity is None
    assert count.method == "unavailable"
    assert "blocks per m2" in count.null_reason


def test_block_count_computes_once_the_factor_is_supplied(thermal):
    from boq.rules import envelope

    factors = Factors.from_dict({"blocks_per_m2": {"thermal_200mm": 12.5}})
    items = envelope.blockwork(thermal, factors)
    count = next(i for i in items if i.id == "block.external.count")
    assert count.method == "derived"
    assert count.quantity == round(529.606 * 12.5)
    assert "12.5 blocks/m2" in count.formula


# -- derived finishes -------------------------------------------------------------------------


def test_plaster_is_two_faces_and_flagged_derived(result):
    plaster = _item(result, "finish.plaster.external")
    assert plaster.quantity == pytest.approx(529.606 * 2)
    assert plaster.method == "derived"
    assert plaster.formula
    assert "derived" in plaster.flags


# -- glazing -----------------------------------------------------------------------------------


def test_glazing_total_matches_the_thermal_calculation(result):
    assert _item(result, "glaz.total").quantity == pytest.approx(146.930)


def test_each_opening_becomes_an_item_with_its_source(result):
    w17 = _item(result, "glaz.window.W17")
    assert w17.quantity == pytest.approx(12.040)
    assert w17.count == 1
    assert w17.source.sheet == "Main"
    assert "size-from-other-set" in w17.flags


# -- unavailable quantities, and why ------------------------------------------------------------


def test_every_null_quantity_carries_a_reason(result):
    for item in result.unavailable:
        assert item.null_reason, f"{item.id} has no null_reason"


def test_pt_slabs_are_not_issued_not_estimated(result):
    pt = _item(result, "conc.slab.pt.first")
    assert pt.quantity is None
    assert "not-issued" in pt.flags
    assert "PT SPECIALIST" in pt.null_reason


def test_thermal_slab_assumption_is_not_promoted(result):
    """The thermal workbook's 200mm slab must not become a structural quantity."""
    pt = _item(result, "conc.slab.pt.first")
    assert "must not be promoted" in pt.null_reason
    assert pt.quantity is None


def test_footing_volume_blocked_on_geometry_not_on_the_tool(result):
    f = _item(result, "conc.footing.strip")
    assert "needs-plan-geometry" in f.flags
    assert "SEE PLAN" in f.null_reason


def test_reason_codes_separate_document_limits_from_tool_limits(result):
    codes = {f for i in result.unavailable for f in i.flags}
    assert {"not-issued", "needs-plan-geometry", "extractor-not-built"} <= codes


def test_roof_insulation_area_is_null_not_substituted(result):
    roof = _item(result, "thermal.insulation.roof")
    assert roof.quantity is None
    assert "not a substitute" in roof.null_reason


def test_ratios_record_the_known_denominator(result):
    ratio = _item(result, "ratio.concrete_per_builtup")
    assert ratio.quantity is None
    assert ratio.spec["denominator_m2"] == 406.9


# -- wastage applied at reporting time only ---------------------------------------------


def test_wastage_never_mutates_the_item(result):
    block = _item(result, "block.external.area")
    before = block.quantity
    factors = Factors.from_dict({"wastage": {"blockwork": 0.05}})
    priced = apply_wastage(block, factors)
    assert block.quantity == before, "the stored quantity must stay net"
    assert priced.net_quantity == before
    assert priced.gross_quantity == pytest.approx(before * 1.05)


def test_wastage_is_not_applied_to_a_null(result):
    assert apply_wastage(_item(result, "conc.slab.pt.first"), Factors.from_dict({})) is None


def test_trades_without_a_wastage_key_are_unchanged(result):
    factors = Factors.from_dict({"wastage": {"blockwork": 0.05}})
    priced = apply_wastage(_item(result, "finish.plaster.external"), factors)
    assert priced.gross_quantity == priced.net_quantity


# -- export gating ----------------------------------------------------------------------


def test_export_is_blocked_while_checks_fail(result):
    assert result.exportable is False
    assert {c.check_id for c in result.blocking} == {
        "window_count_setA_vs_setC",
        "thermal_spreadsheet_errors",
        "slab_spec_structural_vs_thermal",
    }


def test_coverage_summary(result):
    coverage = result.coverage()
    assert coverage["extracted"] > 0
    assert coverage["derived"] > 0
    assert coverage["unavailable"] == len(result.unavailable)


def test_by_trade_groups_items(result):
    trades = result.by_trade()
    assert "blockwork" in trades
    assert "doors_windows" in trades


# -- the item invariants bite ------------------------------------------------------------


def test_null_without_reason_is_rejected():
    with pytest.raises(ValueError, match="null_reason"):
        QuantityItem(
            id="x.y",
            discipline="structural",
            element="e",
            quantity=None,
            unit="m3",
            method="unavailable",
            source=Source(file="f.pdf"),
            confidence=1.0,
        )


def test_derived_without_formula_is_rejected():
    with pytest.raises(ValueError, match="formula"):
        QuantityItem(
            id="x.y",
            discipline="structural",
            element="e",
            quantity=1.0,
            unit="m3",
            method="derived",
            source=Source(file="f.pdf"),
            confidence=1.0,
        )


def test_assumed_without_reference_is_rejected():
    with pytest.raises(ValueError, match="assumption_ref"):
        QuantityItem(
            id="x.y",
            discipline="structural",
            element="e",
            quantity=1.0,
            unit="m3",
            method="assumed",
            source=Source(file="f.pdf"),
            confidence=1.0,
        )


def test_pdf_source_requires_page_and_bbox():
    with pytest.raises(ValueError, match="pdf source"):
        Source(file="f.pdf", file_type="pdf")


def test_xlsx_source_requires_sheet_and_cell():
    with pytest.raises(ValueError, match="xlsx source"):
        Source(file="f.xlsx", file_type="xlsx")
