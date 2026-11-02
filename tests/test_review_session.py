"""Engineer review tests.

The review screen is the mandatory gate before a BoQ leaves the office, so these cover the
audit trail, the correction semantics and -- above all -- that the export gate actually holds.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from boq.extract.architectural import area_schedule
from boq.extract.thermal import thermal_calc
from boq.extract.thermal.workbook import CellMap
from boq.normalize.items import validate
from boq.review.session import ReviewError, ReviewSession, ReviewStatus
from boq.rules import engine
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


def _result():
    payload = json.loads((FIXTURES / "thermal_workbook.cells.json").read_text(encoding="utf-8"))
    thermal = thermal_calc.parse(CellMap.from_dict(payload["sheets"]))
    areas = area_schedule.parse(load_words(FIXTURES / "arch_p05_area_schedule.words.json"))
    return engine.run(
        area_schedule=areas,
        thermal=thermal,
        set_a_window_counts=SET_A_WINDOWS,
        project={"project_no": "DCR2564", "title": "Proposed Two Storey Villa"},
        source_files=[
            {"file": "THERMAL_DCR2564.xlsx", "sha256": "b" * 64, "set": "C", "file_type": "xlsx"}
        ],
    )


@pytest.fixture
def session():
    return ReviewSession(_result())


# -- ordering -------------------------------------------------------------------------


def test_items_are_ordered_lowest_confidence_first(session):
    confidences = [i.confidence for i in session.items]
    assert confidences == sorted(confidences)


def test_ordering_is_stable_for_ties(session):
    tied = [i.id for i in session.items if i.confidence == 0.95]
    assert tied == sorted(tied)


def test_queue_holds_only_unresolved_low_confidence_items(session):
    for item in session.queue:
        assert item.confidence < session.threshold
        assert session.state(item.id).status is ReviewStatus.UNREVIEWED


def test_the_least_confident_item_is_first(session):
    """Paint, at 60%, is the weakest derivation in the project."""
    assert session.items[0].id == "finish.paint.external"


# -- approve --------------------------------------------------------------------------


def test_approve_records_who_and_leaves_the_value_alone(session):
    item = session.item("finish.paint.external")
    before = item.quantity
    session.approve(item.id, by="S.Abbas", comment="checked against elevations")
    state = session.state(item.id)
    assert state.status is ReviewStatus.APPROVED
    assert state.by == "S.Abbas"
    assert item.quantity == before
    assert item.method == "derived"


def test_approving_clears_it_from_the_queue(session):
    item = session.queue[0]
    session.approve(item.id, by="S.Abbas")
    assert item.id not in {i.id for i in session.queue}


def test_an_action_must_name_a_reviewer(session):
    with pytest.raises(ReviewError, match="who performed it"):
        session.approve("finish.paint.external", by="")


# -- correct --------------------------------------------------------------------------


def test_correction_preserves_the_original_value(session):
    item = session.item("finish.plaster.external")
    original = item.quantity
    session.correct(item.id, 900.0, by="S.Abbas", comment="measured off the elevations")
    assert item.quantity == 900.0
    assert session.state(item.id).original_value == original
    assert session.audit[-1].from_value == original
    assert session.audit[-1].to_value == 900.0


def test_correction_becomes_an_assumption(session):
    """An engineer-supplied number is an assumption, whatever produced the original."""
    item = session.item("finish.plaster.external")
    session.correct(item.id, 900.0, by="S.Abbas")
    assert item.method == "assumed"
    assert item.assumption_ref == "engineer-review:S.Abbas"
    assert "engineer-corrected" in item.flags


def test_correction_notes_record_the_previous_method(session):
    item = session.item("finish.plaster.external")
    session.correct(item.id, 900.0, by="S.Abbas")
    assert "was derived" in item.notes


def test_an_unavailable_item_can_be_given_a_value(session):
    """Supplying a footing length by hand is exactly what this screen is for."""
    item = session.item("conc.footing.strip")
    assert item.quantity is None
    session.correct(item.id, 12.5, by="S.Abbas", comment="scaled off the foundation plan")
    assert item.quantity == 12.5
    assert item.null_reason is None
    assert item.method == "assumed"


@pytest.mark.parametrize("bad", [-1.0, "abc", True, None])
def test_bad_corrections_are_refused(session, bad):
    with pytest.raises(ReviewError):
        session.correct("finish.paint.external", bad, by="S.Abbas")


# -- reject ---------------------------------------------------------------------------


def test_reject_nulls_the_quantity_with_the_reviewers_reason(session):
    item = session.item("finish.paint.external")
    session.reject(item.id, by="S.Abbas", comment="no paint schedule exists")
    assert item.quantity is None
    assert item.method == "unavailable"
    assert "no paint schedule exists" in item.null_reason
    assert "S.Abbas" in item.null_reason


def test_a_rejection_must_say_why(session):
    with pytest.raises(ReviewError, match="must say why"):
        session.reject("finish.paint.external", by="S.Abbas", comment="  ")


# -- audit trail -----------------------------------------------------------------------


def test_audit_is_append_only_and_ordered(session):
    session.approve("finish.paint.external", by="A")
    session.correct("finish.plaster.external", 900.0, by="B")
    session.reject("glaz.window.W17", by="C", comment="duplicate")
    assert [a.action for a in session.audit] == ["approve", "correct", "reject"]
    assert [a.by for a in session.audit] == ["A", "B", "C"]


def test_audit_entries_are_immutable(session):
    session.approve("finish.paint.external", by="A")
    with pytest.raises((AttributeError, TypeError)):
        session.audit[0].by = "someone else"


def test_audit_survives_a_round_trip(session, tmp_path):
    session.approve("finish.paint.external", by="A", comment="ok")
    session.correct("finish.plaster.external", 900.0, by="B", comment="measured")
    path = tmp_path / "audit.json"
    session.save_audit(path)
    loaded = ReviewSession.load_audit(path)
    assert [a.to_dict() for a in loaded] == [a.to_dict() for a in session.audit]


def test_repeated_review_of_one_item_keeps_the_whole_history(session):
    session.approve("finish.paint.external", by="A")
    session.correct("finish.paint.external", 1000.0, by="B", comment="revised")
    entries = [a for a in session.audit if a.item_id == "finish.paint.external"]
    assert len(entries) == 2
    assert entries[1].from_value == entries[0].to_value


# -- export gating ---------------------------------------------------------------------


def test_export_is_blocked_at_the_start(session):
    assert not session.can_export
    assert session.export_blockers()


def test_low_confidence_items_block_export_by_themselves(session):
    for check in session.cross_checks:
        check.blocking = False
    assert not session.can_export
    assert all("threshold" in b for b in session.export_blockers())


def test_resolving_everything_opens_the_gate(session):
    for item in list(session.queue):
        session.approve(item.id, by="S.Abbas")
    for check in session.outstanding_checks():
        session.resolve_check(check.check_id, by="S.Abbas", comment="accepted, see file note")
    assert session.can_export
    assert session.export_blockers() == []


def test_accepting_a_check_keeps_its_failing_status(session):
    """The documents still disagree; what changes is that someone owns the decision."""
    check = session.outstanding_checks()[0]
    session.resolve_check(check.check_id, by="S.Abbas", comment="client confirmed")
    assert check.status in ("fail", "not_possible")
    assert not check.blocking
    assert "accepted by S.Abbas" in check.detail


def test_accepting_a_check_is_audited(session):
    check = session.outstanding_checks()[0]
    session.resolve_check(check.check_id, by="S.Abbas", comment="client confirmed")
    assert session.audit[-1].action == "accept-cross-check"


def test_accepting_a_check_must_say_why(session):
    check = session.outstanding_checks()[0]
    with pytest.raises(ReviewError, match="must say why"):
        session.resolve_check(check.check_id, by="S.Abbas", comment="")


def test_unknown_ids_are_rejected(session):
    with pytest.raises(ReviewError, match="unknown item"):
        session.approve("no.such.item", by="A")
    with pytest.raises(ReviewError, match="unknown cross-check"):
        session.resolve_check("no_such_check", by="A", comment="x")


# -- document output --------------------------------------------------------------------


def test_document_carries_review_state_and_stays_schema_valid(session):
    session.approve("finish.paint.external", by="S.Abbas", comment="ok")
    session.correct("finish.plaster.external", 900.0, by="S.Abbas")
    doc = session.to_document()
    assert validate(doc) == []

    by_id = {i["id"]: i for i in doc["items"]}
    assert by_id["finish.paint.external"]["review"]["status"] == "approved"
    corrected = by_id["finish.plaster.external"]
    assert corrected["review"]["status"] == "corrected"
    assert corrected["review"]["original_value"] == pytest.approx(1059.212)
    assert corrected["method"] == "assumed"


def test_document_review_status_reflects_the_gate(session):
    assert session.to_document()["extraction"]["review_status"] == "in_review"
    for item in list(session.queue):
        session.approve(item.id, by="S.Abbas")
    for check in session.outstanding_checks():
        session.resolve_check(check.check_id, by="S.Abbas", comment="accepted")
    assert session.to_document()["extraction"]["review_status"] == "approved"


def test_summary_reports_progress(session):
    session.approve("finish.paint.external", by="A")
    summary = session.summary()
    assert summary["total_items"] == len(session.items)
    assert summary["by_status"]["approved"] == 1
    assert summary["can_export"] is False
