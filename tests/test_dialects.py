"""Tests for the warehouse model.

Mostly structural. The field values are claims about products and the tests
cannot check them against the vendors, so what they check is that the model
stays internally consistent and that every claim carries its note.
"""

from __future__ import annotations

import dataclasses

import pytest

from sdd.dialects import (
    DIALECTS,
    DIVERGENCE_AXES,
    DivideByZero,
    NullOrder,
    UnknownDialectError,
    dialect,
)


def test_every_dialect_is_keyed_by_its_own_name():
    assert all(name == entry.name for name, entry in DIALECTS.items())


def test_six_warehouses_are_modelled():
    assert len(DIALECTS) == 6


def test_every_dialect_carries_a_note():
    """A claim about somebody's product without a source is folklore with a dataclass."""
    assert all(entry.note.strip() for entry in DIALECTS.values())


def test_the_divergence_axes_are_exactly_the_behavioural_fields():
    """Adding a field without deciding whether it is an axis fails here."""
    fields = {field.name for field in dataclasses.fields(DIALECTS["postgres"])}
    assert fields - {"name", "note"} == set(DIVERGENCE_AXES)


def test_descending_null_order_inverts_ascending():
    for entry in DIALECTS.values():
        assert entry.null_order_desc != entry.null_order_asc


def test_bigquery_sorts_nulls_first_ascending():
    assert DIALECTS["bigquery"].null_order_asc is NullOrder.FIRST


def test_postgres_sorts_nulls_last_ascending():
    assert DIALECTS["postgres"].null_order_asc is NullOrder.LAST


def test_redshift_inherits_postgres_arithmetic():
    assert DIALECTS["redshift"].integer_division is DIALECTS["postgres"].integer_division


def test_mysql_is_the_only_warehouse_that_does_not_raise_on_division_by_zero():
    raising = [name for name, entry in DIALECTS.items() if entry.divide_by_zero is DivideByZero.RAISE]
    assert set(DIALECTS) - set(raising) == {"mysql"}


def test_oracle_is_the_only_warehouse_where_the_empty_string_is_null():
    odd = [name for name, entry in DIALECTS.items() if entry.empty_string_is_null]
    assert odd == ["oracle"]


def test_at_least_two_warehouses_differ_on_every_axis():
    """An axis nothing differs on would inflate the suite without measuring anything."""
    for axis in DIVERGENCE_AXES:
        values = {getattr(entry, axis) for entry in DIALECTS.values()}
        assert len(values) > 1, axis


def test_looking_up_a_dialect_by_name_works():
    assert dialect("snowflake").name == "snowflake"


def test_an_unknown_dialect_lists_the_known_ones():
    with pytest.raises(UnknownDialectError, match="available: bigquery"):
        dialect("duckdb")
