"""Canonical quantity items -- the contract defined by schema/project_quantities.v1.json.

Everything the rules engine emits is a :class:`QuantityItem`. The schema's guardrails are
mirrored here as runtime invariants so a malformed item cannot be constructed in the first
place, rather than only failing validation at the end of a run.
"""

from __future__ import annotations

import datetime as _dt
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

SCHEMA_VERSION = "1.2.0"
SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "project_quantities.v1.json"

Method = Literal["extracted", "derived", "assumed", "unavailable"]

UNITS = {"m", "m2", "m3", "kg", "tonne", "nr", "percent", "W/m2K"}


@dataclass(frozen=True, slots=True)
class Source:
    """Where a value physically came from. No number is emitted without one."""

    file: str
    file_type: Literal["pdf", "xlsx", "dwf", "dxf", "image"] | None = None
    page: int | None = None
    sheet: str | None = None
    region: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    cell: str | None = None

    def __post_init__(self) -> None:
        if self.file_type == "pdf" and (self.page is None or self.bbox is None):
            raise ValueError(f"pdf source needs page and bbox: {self.file}")
        if self.file_type == "xlsx" and (self.sheet is None or self.cell is None):
            raise ValueError(f"xlsx source needs sheet and cell: {self.file}")

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"file": self.file}
        for key in ("file_type", "page", "sheet", "region", "cell"):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        if self.bbox is not None:
            out["bbox"] = list(self.bbox)
        return out


@dataclass
class QuantityItem:
    """One measurable quantity, traceable to its source."""

    id: str
    discipline: Literal["structural", "architectural", "thermal", "mep", "general"]
    element: str
    quantity: float | None
    unit: str | None
    method: Method
    source: Source
    confidence: float
    trade: str | None = None
    mark: str | None = None
    level: str | None = None
    elevation: str | None = None
    count: int | None = None
    spec: dict[str, Any] = field(default_factory=dict)
    null_reason: str | None = None
    formula: str | None = None
    derived_from: list[str] = field(default_factory=list)
    assumption_ref: str | None = None
    additional_sources: list[Source] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    cross_checks: list[str] = field(default_factory=list)
    review: dict[str, Any] | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        if self.quantity is None and not self.null_reason:
            raise ValueError(f"{self.id}: a null quantity requires null_reason")
        if self.method == "derived" and not self.formula:
            raise ValueError(f"{self.id}: a derived quantity requires formula")
        if self.method == "assumed" and not self.assumption_ref:
            raise ValueError(f"{self.id}: an assumed quantity requires assumption_ref")
        if self.unit is not None and self.unit not in UNITS:
            raise ValueError(f"{self.id}: unknown unit {self.unit!r}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"{self.id}: confidence must be within 0..1")

    @property
    def is_available(self) -> bool:
        return self.quantity is not None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "discipline": self.discipline,
            "element": self.element,
            "quantity": self.quantity,
            "unit": self.unit,
            "method": self.method,
            "source": self.source.to_dict(),
            "confidence": self.confidence,
        }
        for key in (
            "trade",
            "mark",
            "level",
            "elevation",
            "count",
            "null_reason",
            "formula",
            "assumption_ref",
        ):
            val = getattr(self, key)
            if val is not None:
                out[key] = val
        if self.spec:
            out["spec"] = self.spec
        if self.derived_from:
            out["derived_from"] = list(self.derived_from)
        if self.additional_sources:
            out["additional_sources"] = [s.to_dict() for s in self.additional_sources]
        if self.flags:
            out["flags"] = list(self.flags)
        if self.cross_checks:
            out["cross_checks"] = list(self.cross_checks)
        if self.review:
            out["review"] = dict(self.review)
        if self.notes:
            out["notes"] = self.notes
        return out


def build_document(
    *,
    project: dict[str, Any],
    items: list[QuantityItem],
    source_files: list[dict[str, Any]],
    tool_version: str = "0.1.0",
    rate_library_version: str | None = None,
    factors_version: str | None = None,
    review_status: str = "draft",
    cross_checks: list[Any] | None = None,
    extracted_at: str | None = None,
) -> dict[str, Any]:
    """Assemble a complete, schema-shaped project quantities document."""
    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project": project,
        "extraction": {
            "extracted_at": extracted_at
            or _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat(),
            "tool_version": tool_version,
            "rate_library_version": rate_library_version,
            "factors_version": factors_version,
            "review_status": review_status,
            "source_files": source_files,
        },
        "items": [i.to_dict() for i in items],
    }
    if cross_checks:
        doc["cross_checks"] = [_check_to_dict(c) for c in cross_checks]
    return doc


def _check_to_dict(check: Any) -> dict[str, Any]:
    if isinstance(check, dict):
        return check
    out: dict[str, Any] = {
        "check_id": check.check_id,
        "description": check.description,
        "status": check.status,
    }
    for key in ("left", "right", "tolerance", "deviation_pct"):
        val = getattr(check, key, None)
        if val is not None:
            out[key] = val
    if getattr(check, "detail", ""):
        out["detail"] = check.detail
    if getattr(check, "item_ids", None):
        out["item_ids"] = list(check.item_ids)
    out["blocking"] = bool(getattr(check, "blocking", False))
    return out


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate(document: dict[str, Any]) -> list[str]:
    """Validate against the v1 schema. Returns human-readable errors; empty means valid."""
    import jsonschema

    validator = jsonschema.Draft202012Validator(_schema())
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    ]
