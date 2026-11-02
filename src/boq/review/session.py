"""Engineer review: the mandatory gate between extraction and BoQ issue.

Build prompt section 7. Three rules shape this module:

* Items are worked **lowest confidence first** -- that is where the errors are.
* Every change is recorded in an **append-only audit trail**: who, what, when, from what
  to what. A correction never silently overwrites the extracted value.
* **Nothing exports** until every low-confidence item has been approved or corrected and no
  blocking cross-check is outstanding.

A correction also changes an item's ``method`` to ``assumed``. An engineer-supplied number is
an assumption, whatever produced the original, and it belongs on the Assumptions sheet of the
BoQ rather than passing as an extracted fact.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from boq.crosscheck.checks import CheckResult, blocking_failures
from boq.normalize.items import QuantityItem, build_document

DEFAULT_CONFIDENCE_THRESHOLD = 0.80


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    APPROVED = "approved"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class ReviewError(Exception):
    """Raised when a review action cannot be applied."""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One immutable record of a review action."""

    at: str
    by: str
    item_id: str
    action: str
    from_value: float | None = None
    to_value: float | None = None
    from_method: str | None = None
    comment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewState:
    status: ReviewStatus = ReviewStatus.UNREVIEWED
    by: str | None = None
    at: str | None = None
    original_value: float | None = None
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "by": self.by,
            "at": self.at,
            "original_value": self.original_value,
            "comment": self.comment,
        }


def _now() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat()


class ReviewSession:
    """A review pass over one project's extracted quantities."""

    def __init__(
        self,
        result,
        *,
        threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        project: dict[str, Any] | None = None,
        source_files: list[dict[str, Any]] | None = None,
    ) -> None:
        self._items: dict[str, QuantityItem] = {i.id: i for i in result.items}
        self._order: list[str] = [i.id for i in self._sorted(result.items)]
        self._state: dict[str, ReviewState] = {i.id: ReviewState() for i in result.items}
        self._audit: list[AuditEntry] = []
        self.threshold = threshold
        self.cross_checks: list[CheckResult] = list(result.cross_checks)
        self.project = project or result.document.get("project", {})
        self.source_files = source_files or result.document["extraction"].get("source_files", [])

    # -- ordering ------------------------------------------------------------------

    @staticmethod
    def _sorted(items: list[QuantityItem]) -> list[QuantityItem]:
        """Lowest confidence first; ties broken by id so the order is stable."""
        return sorted(items, key=lambda i: (i.confidence, i.id))

    @property
    def items(self) -> list[QuantityItem]:
        """Every item, lowest confidence first."""
        return [self._items[i] for i in self._order]

    def item(self, item_id: str) -> QuantityItem:
        if item_id not in self._items:
            raise ReviewError(f"unknown item {item_id!r}")
        return self._items[item_id]

    def state(self, item_id: str) -> ReviewState:
        if item_id not in self._state:
            raise ReviewError(f"unknown item {item_id!r}")
        return self._state[item_id]

    # -- what still needs attention --------------------------------------------------

    def needs_review(self, item_id: str) -> bool:
        """True when an item is below the confidence threshold and not yet dealt with."""
        item = self.item(item_id)
        if item.confidence >= self.threshold:
            return False
        return self._state[item_id].status is ReviewStatus.UNREVIEWED

    @property
    def queue(self) -> list[QuantityItem]:
        """Outstanding low-confidence items, lowest confidence first."""
        return [i for i in self.items if self.needs_review(i.id)]

    @property
    def reviewed_count(self) -> int:
        return sum(1 for s in self._state.values() if s.status is not ReviewStatus.UNREVIEWED)

    # -- actions ----------------------------------------------------------------------

    def approve(self, item_id: str, by: str, comment: str = "") -> AuditEntry:
        """Accept the extracted value as correct."""
        item = self.item(item_id)
        self._require_reviewer(by)
        entry = AuditEntry(
            at=_now(),
            by=by,
            item_id=item_id,
            action="approve",
            from_value=item.quantity,
            to_value=item.quantity,
            comment=comment,
        )
        self._state[item_id] = ReviewState(
            status=ReviewStatus.APPROVED, by=by, at=entry.at, comment=comment or None
        )
        self._audit.append(entry)
        return entry

    def correct(self, item_id: str, value: float, by: str, comment: str = "") -> AuditEntry:
        """Replace a quantity with an engineer-supplied value.

        The original is preserved on the review record and in the audit trail, and the item
        becomes ``assumed`` so the BoQ reports it as an assumption rather than an extraction.
        """
        item = self.item(item_id)
        self._require_reviewer(by)
        if value is None:
            raise ReviewError("a correction needs a value; use reject() to discard an item")
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ReviewError(f"correction value must be numeric, got {value!r}")
        if value < 0:
            raise ReviewError("a quantity cannot be negative")

        original = item.quantity
        original_method = item.method

        entry = AuditEntry(
            at=_now(),
            by=by,
            item_id=item_id,
            action="correct",
            from_value=original,
            to_value=float(value),
            from_method=original_method,
            comment=comment,
        )

        item.quantity = float(value)
        item.method = "assumed"
        item.assumption_ref = f"engineer-review:{by}"
        item.null_reason = None
        if "engineer-corrected" not in item.flags:
            item.flags.append("engineer-corrected")
        note = f"Corrected by {by} from {original!r} (was {original_method})."
        item.notes = f"{item.notes} {note}".strip() if item.notes else note

        self._state[item_id] = ReviewState(
            status=ReviewStatus.CORRECTED,
            by=by,
            at=entry.at,
            original_value=original,
            comment=comment or None,
        )
        self._audit.append(entry)
        return entry

    def reject(self, item_id: str, by: str, comment: str) -> AuditEntry:
        """Discard an item: it is wrong and has no replacement value.

        The quantity becomes null with the reviewer's reason, so the BoQ excludes it rather
        than carrying a figure nobody stands behind.
        """
        item = self.item(item_id)
        self._require_reviewer(by)
        if not comment.strip():
            raise ReviewError("a rejection must say why")

        original = item.quantity
        entry = AuditEntry(
            at=_now(),
            by=by,
            item_id=item_id,
            action="reject",
            from_value=original,
            to_value=None,
            from_method=item.method,
            comment=comment,
        )

        item.quantity = None
        item.method = "unavailable"
        item.null_reason = f"rejected in review by {by}: {comment}"
        item.formula = None
        item.assumption_ref = None
        if "engineer-rejected" not in item.flags:
            item.flags.append("engineer-rejected")

        self._state[item_id] = ReviewState(
            status=ReviewStatus.REJECTED,
            by=by,
            at=entry.at,
            original_value=original,
            comment=comment,
        )
        self._audit.append(entry)
        return entry

    @staticmethod
    def _require_reviewer(by: str) -> None:
        if not by or not by.strip():
            raise ReviewError("every review action must record who performed it")

    # -- export gating ------------------------------------------------------------------

    def outstanding_checks(self) -> list[CheckResult]:
        return blocking_failures(self.cross_checks)

    def export_blockers(self) -> list[str]:
        """Everything standing between this project and an issued BoQ."""
        blockers = [
            f"{i.id}: confidence {i.confidence:.0%} is below the {self.threshold:.0%} "
            f"threshold and has not been approved or corrected"
            for i in self.queue
        ]
        blockers += [f"cross-check {c.check_id}: {c.detail}" for c in self.outstanding_checks()]
        return blockers

    @property
    def can_export(self) -> bool:
        return not self.export_blockers()

    def resolve_check(self, check_id: str, by: str, comment: str) -> AuditEntry:
        """Record an engineer's acceptance of a failing cross-check.

        The check keeps its failing status -- the documents really do disagree -- but it stops
        blocking export once someone has put their name to that decision.
        """
        self._require_reviewer(by)
        if not comment.strip():
            raise ReviewError("accepting a failed cross-check must say why")
        check = next((c for c in self.cross_checks if c.check_id == check_id), None)
        if check is None:
            raise ReviewError(f"unknown cross-check {check_id!r}")
        check.blocking = False
        check.detail = f"{check.detail} | accepted by {by}: {comment}"
        entry = AuditEntry(
            at=_now(), by=by, item_id=check_id, action="accept-cross-check", comment=comment
        )
        self._audit.append(entry)
        return entry

    # -- output ----------------------------------------------------------------------------

    @property
    def audit(self) -> tuple[AuditEntry, ...]:
        """The append-only audit trail, oldest first."""
        return tuple(self._audit)

    def to_document(self, **kwargs: Any) -> dict[str, Any]:
        """A schema-shaped document carrying review state on every item."""
        for item_id, state in self._state.items():
            self._items[item_id].review = state.to_dict()

        doc = build_document(
            project=self.project,
            items=self.items,
            source_files=self.source_files,
            review_status="approved" if self.can_export else "in_review",
            cross_checks=self.cross_checks,
            **kwargs,
        )
        return doc

    def save_audit(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "project": self.project.get("project_no"),
                    "threshold": self.threshold,
                    "entries": [e.to_dict() for e in self._audit],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def load_audit(path: str | Path) -> list[AuditEntry]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return [AuditEntry(**e) for e in payload["entries"]]

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for state in self._state.values():
            counts[state.status.value] = counts.get(state.status.value, 0) + 1
        return {
            "total_items": len(self._items),
            "by_status": counts,
            "outstanding_low_confidence": len(self.queue),
            "outstanding_checks": [c.check_id for c in self.outstanding_checks()],
            "can_export": self.can_export,
        }
