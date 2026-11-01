"""Rate library tests."""

from __future__ import annotations

import pytest

from boq.normalize.items import QuantityItem, Source
from boq.rates.library import PriceBand, RateLibrary

SAMPLE = {
    "version": "2026.11-draft",
    "currency": "BHD",
    "decimals": 3,
    "effective_date": "2026-11-01",
    "items": [
        {
            "code": "BLK.200",
            "description": "200mm thermal block wall",
            "unit": "m2",
            "material_only": {"low": 3.100, "expected": 3.450, "high": 3.900},
            "supply_and_fix": {"low": 5.200, "expected": 5.750, "high": 6.400},
            "supplier": "Al Manaratain",
            "quoted_on": "2026-10-12",
        },
        {
            "code": "PLS.EXT",
            "description": "External plaster rendering",
            "unit": "m2",
            "supply_and_fix": {"expected": 2.250},
        },
        {"code": "NOPRICE", "description": "Placeholder", "unit": "m2"},
        {
            "code": "WRONGUNIT",
            "description": "Priced in m3",
            "unit": "m3",
            "supply_and_fix": {"expected": 10.0},
        },
    ],
    "mapping": {
        "block.external.area": "BLK.200",
        "finish.plaster.external": "PLS.EXT",
        "glaz.window": "NOPRICE",
        "area": "WRONGUNIT",
    },
}


def _item(item_id: str, unit: str = "m2") -> QuantityItem:
    return QuantityItem(
        id=item_id,
        discipline="architectural",
        element="e",
        quantity=10.0,
        unit=unit,
        method="extracted",
        source=Source(file="f.xlsx"),
        confidence=0.9,
    )


@pytest.fixture
def lib() -> RateLibrary:
    return RateLibrary.from_dict(SAMPLE)


def test_metadata(lib):
    assert lib.version == "2026.11-draft"
    assert lib.currency == "BHD"
    assert lib.decimals == 3
    assert len(lib) == 4


def test_price_levels(lib):
    rate = lib.get("BLK.200")
    assert rate.price("supply_and_fix", "low") == 5.200
    assert rate.price("supply_and_fix", "expected") == 5.750
    assert rate.price("supply_and_fix", "high") == 6.400
    assert rate.price("material_only", "expected") == 3.450


def test_partial_band_leaves_other_levels_none(lib):
    rate = lib.get("PLS.EXT")
    assert rate.price("supply_and_fix", "expected") == 2.250
    assert rate.price("supply_and_fix", "low") is None
    assert rate.material_only.is_empty


def test_scalar_price_fills_all_levels():
    band = PriceBand.from_any(4.0)
    assert (band.low, band.expected, band.high) == (4.0, 4.0, 4.0)


def test_match_by_exact_id(lib):
    assert lib.match(_item("block.external.area")).code == "BLK.200"


def test_match_by_longest_prefix(lib):
    """glaz.window.W17 is priced by the glaz.window rule, not per mark."""
    assert lib.match(_item("glaz.window.W17")).code == "NOPRICE"


def test_longest_prefix_wins():
    lib = RateLibrary.from_dict(
        {
            "items": [
                {"code": "GENERIC", "unit": "m2", "supply_and_fix": {"expected": 1.0}},
                {"code": "SPECIFIC", "unit": "m2", "supply_and_fix": {"expected": 2.0}},
            ],
            "mapping": {"glaz": "GENERIC", "glaz.window": "SPECIFIC"},
        }
    )
    assert lib.match(_item("glaz.window.W17")).code == "SPECIFIC"


def test_prefix_does_not_match_a_partial_segment(lib):
    """'area' must not match 'areaway.something' -- only whole dotted segments."""
    assert lib.code_for("areaway.foo") is None


def test_unmatched_item_requires_a_rate(lib):
    matched = lib.match(_item("unknown.thing"))
    assert matched.rate is None
    assert matched.rate_required


def test_matched_but_unpriced_requires_a_rate(lib):
    matched = lib.match(_item("glaz.window.W17"))
    assert matched.rate is not None
    assert matched.rate_required, "a rate entry with no price is still 'rate required'"


def test_unit_mismatch_is_flagged_not_converted(lib):
    matched = lib.match(_item("area.plot", unit="m2"))
    assert matched.unit_mismatch
    assert matched.rate_required


def test_the_shipped_library_is_empty_by_design():
    """Guardrail: no invented prices. The repo ships with no rates."""
    lib = RateLibrary.load()
    assert lib.is_empty
    assert lib.currency == "BHD"
    assert lib.decimals == 3


def test_every_item_is_rate_required_against_the_shipped_library():
    lib = RateLibrary.load()
    assert lib.match(_item("block.external.area")).rate_required
