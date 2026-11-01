"""Configurable factors, and the reporting-time application of wastage.

Build prompt section 5: wastage and lap allowances are **configurable multipliers applied at
reporting time only, never baked into the extracted quantity.** This module is the only place
they are applied, and it never mutates an item -- it returns a separate reporting view.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from boq.normalize.items import QuantityItem

CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "factors.yaml"

# Which wastage key applies to which trade.
_WASTAGE_BY_TRADE = {
    "substructure": "concrete",
    "superstructure_concrete": "concrete",
    "reinforcement": "rebar",
    "blockwork": "blockwork",
}


@dataclass(frozen=True, slots=True)
class PricedQuantity:
    """An item's quantity as it appears in the BoQ, after wastage.

    Keeps the net quantity visible alongside the gross so the estimator can see what was
    added and why.
    """

    item_id: str
    net_quantity: float
    wastage_factor: float
    gross_quantity: float
    wastage_key: str | None
    unit: str | None

    @property
    def wastage_pct(self) -> float:
        return self.wastage_factor * 100


class Factors:
    """Loaded contents of config/factors.yaml."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @classmethod
    def load(cls, path: Path | str | None = None) -> Factors:
        import yaml

        target = Path(path) if path else CONFIG_PATH
        return cls(yaml.safe_load(target.read_text(encoding="utf-8")) or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Factors:
        return cls(data)

    @property
    def version(self) -> str | None:
        return self._data.get("version")

    def wastage(self, key: str) -> float:
        return float(self._data.get("wastage", {}).get(key, 0.0))

    def rebar_unit_mass(self, diameter_mm: int) -> float | None:
        table = self._data.get("rebar_unit_mass_kg_per_m", {})
        value = table.get(diameter_mm, table.get(str(diameter_mm)))
        return None if value is None else float(value)

    def blocks_per_m2(self, block_type: str) -> float | None:
        """Blocks per square metre, or None if the office has not supplied the figure.

        A None here is deliberate and must propagate as a null quantity with a reason. No
        default is invented.
        """
        value = self._data.get("blocks_per_m2", {}).get(block_type)
        return None if value is None else float(value)

    def storey_height(self, level: str) -> float | None:
        value = self._data.get("storey_heights_m", {}).get(level)
        return None if value is None else float(value)

    def get(self, *path: str, default: Any = None) -> Any:
        node: Any = self._data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node


@lru_cache(maxsize=1)
def default_factors() -> Factors:
    return Factors.load()


def apply_wastage(item: QuantityItem, factors: Factors) -> PricedQuantity | None:
    """The reporting view of ``item`` with its trade's wastage applied.

    Returns None for an item with no quantity -- there is nothing to gross up, and inventing
    a figure for a null is exactly what the guardrails forbid. The item itself is never
    modified.
    """
    if item.quantity is None:
        return None

    key = _WASTAGE_BY_TRADE.get(item.trade or "")
    factor = factors.wastage(key) if key else 0.0
    return PricedQuantity(
        item_id=item.id,
        net_quantity=item.quantity,
        wastage_factor=factor,
        gross_quantity=item.quantity * (1.0 + factor),
        wastage_key=key,
        unit=item.unit,
    )


def apply_all(items: list[QuantityItem], factors: Factors) -> list[PricedQuantity]:
    """Reporting views for every item that has a quantity."""
    return [p for p in (apply_wastage(i, factors) for i in items) if p is not None]
