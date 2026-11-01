"""Rate library.

Build prompt section 6. Three rules drive the design:

* **Prices are never invented.** An item with no rate gets a blank rate and a
  "rate required" flag -- never a plausible-looking number.
* Rates are **versioned**, and every BoQ records which library version priced it.
* Each item carries **low / expected / high** levels so a quotation can show a range, for
  both material-only and supply-and-fix where the library provides them.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

RATES_PATH = Path(__file__).resolve().parents[3] / "rates" / "rates.yaml"

Level = Literal["low", "expected", "high"]
Basis = Literal["material_only", "supply_and_fix"]

LEVELS: tuple[Level, ...] = ("low", "expected", "high")


@dataclass(frozen=True, slots=True)
class PriceBand:
    low: float | None = None
    expected: float | None = None
    high: float | None = None

    @property
    def is_empty(self) -> bool:
        return self.low is None and self.expected is None and self.high is None

    def at(self, level: Level) -> float | None:
        return getattr(self, level)

    @classmethod
    def from_any(cls, data: Any) -> PriceBand:
        if data is None:
            return cls()
        if isinstance(data, int | float):
            value = float(data)
            return cls(low=value, expected=value, high=value)
        if isinstance(data, dict):
            return cls(
                low=_opt_float(data.get("low")),
                expected=_opt_float(data.get("expected")),
                high=_opt_float(data.get("high")),
            )
        raise TypeError(f"cannot read a price band from {data!r}")


def _opt_float(value: Any) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class Rate:
    code: str
    description: str
    unit: str | None
    material_only: PriceBand
    supply_and_fix: PriceBand
    supplier: str | None = None
    quoted_on: str | None = None
    source_note: str | None = None

    def band(self, basis: Basis) -> PriceBand:
        return self.material_only if basis == "material_only" else self.supply_and_fix

    def price(self, basis: Basis, level: Level) -> float | None:
        return self.band(basis).at(level)

    @property
    def has_any_price(self) -> bool:
        return not (self.material_only.is_empty and self.supply_and_fix.is_empty)


@dataclass(frozen=True, slots=True)
class RatedItem:
    """A quantity item matched against the rate library."""

    item_id: str
    rate: Rate | None
    rate_required: bool
    unit_mismatch: bool = False

    @property
    def code(self) -> str | None:
        return self.rate.code if self.rate else None


class RateLibrary:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data or {}
        self._rates: dict[str, Rate] = {}
        for entry in self._data.get("items") or []:
            rate = Rate(
                code=str(entry["code"]),
                description=str(entry.get("description", "")),
                unit=entry.get("unit"),
                material_only=PriceBand.from_any(entry.get("material_only")),
                supply_and_fix=PriceBand.from_any(entry.get("supply_and_fix")),
                supplier=entry.get("supplier") or None,
                quoted_on=str(entry["quoted_on"]) if entry.get("quoted_on") else None,
                source_note=entry.get("source_note") or None,
            )
            self._rates[rate.code] = rate
        self._mapping: dict[str, str] = {
            str(k): str(v) for k, v in (self._data.get("mapping") or {}).items()
        }

    # -- loading -----------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | str | None = None) -> RateLibrary:
        import yaml

        target = Path(path) if path else RATES_PATH
        return cls(yaml.safe_load(target.read_text(encoding="utf-8")) or {})

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RateLibrary:
        return cls(data)

    # -- metadata ----------------------------------------------------------------

    @property
    def version(self) -> str:
        return str(self._data.get("version", "0.0.0"))

    @property
    def currency(self) -> str:
        return str(self._data.get("currency", "BHD"))

    @property
    def decimals(self) -> int:
        return int(self._data.get("decimals", 3))

    @property
    def effective_date(self) -> str | None:
        value = self._data.get("effective_date")
        return str(value) if value else None

    @property
    def is_empty(self) -> bool:
        return not self._rates

    def __len__(self) -> int:
        return len(self._rates)

    def codes(self) -> list[str]:
        return sorted(self._rates)

    def get(self, code: str) -> Rate | None:
        return self._rates.get(code)

    # -- matching ----------------------------------------------------------------

    def code_for(self, item_id: str) -> str | None:
        """Resolve a quantity item id to a rate code.

        Matching is by longest prefix, so ``glaz.window.W17`` can be priced by a rule on
        ``glaz.window`` without an entry per mark.
        """
        if item_id in self._mapping:
            return self._mapping[item_id]
        candidates = [k for k in self._mapping if item_id.startswith(f"{k}.")]
        if not candidates:
            return None
        return self._mapping[max(candidates, key=len)]

    def match(self, item) -> RatedItem:
        """Match one :class:`~boq.normalize.items.QuantityItem` against the library.

        An unmatched item, an unpriced rate, or a rate whose unit disagrees with the item's
        all produce ``rate_required``. A unit mismatch never silently converts.
        """
        code = self.code_for(item.id)
        rate = self.get(code) if code else None

        if rate is None:
            return RatedItem(item_id=item.id, rate=None, rate_required=True)

        mismatch = bool(rate.unit and item.unit and rate.unit != item.unit)
        return RatedItem(
            item_id=item.id,
            rate=rate,
            rate_required=mismatch or not rate.has_any_price,
            unit_mismatch=mismatch,
        )

    def match_all(self, items) -> dict[str, RatedItem]:
        return {i.id: self.match(i) for i in items}


def default_library() -> RateLibrary:
    return RateLibrary.load()
