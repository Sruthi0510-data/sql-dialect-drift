"""Tests for the value model, which exists so NULL cannot be mistaken for None."""

from __future__ import annotations

import pytest

from sdd.values import NULL, NullType, SqlTypeError, Truth, is_null, truth_of, type_name


def test_null_is_a_singleton():
    assert NullType() is NULL


def test_null_reprs_as_null():
    assert repr(NULL) == "NULL"


def test_null_has_no_truth_value():
    """`if value:` on a NULL is a bug, so it fails loudly rather than being truthy."""
    with pytest.raises(SqlTypeError, match="no truth value"):
        bool(NULL)


def test_null_reads_as_unknown():
    assert truth_of(NULL) is Truth.UNKNOWN


def test_zero_is_false_and_one_is_true():
    assert truth_of(0) is Truth.FALSE and truth_of(1) is Truth.TRUE


def test_booleans_read_as_themselves():
    assert truth_of(True) is Truth.TRUE and truth_of(False) is Truth.FALSE


def test_a_float_reads_as_a_number():
    assert truth_of(0.0) is Truth.FALSE and truth_of(0.5) is Truth.TRUE


def test_a_string_has_no_truth_value():
    with pytest.raises(SqlTypeError, match="no truth value"):
        truth_of("yes")


def test_a_where_clause_keeps_only_true():
    assert Truth.TRUE.keeps_row()
    assert not Truth.FALSE.keeps_row()
    assert not Truth.UNKNOWN.keeps_row()


def test_a_constraint_rejects_only_false():
    """The asymmetry that makes UNKNOWN worth modelling separately."""
    assert Truth.TRUE.passes_constraint()
    assert Truth.UNKNOWN.passes_constraint()
    assert not Truth.FALSE.passes_constraint()


def test_negation_leaves_unknown_unknown():
    assert Truth.UNKNOWN.negate() is Truth.UNKNOWN


def test_negation_flips_the_other_two():
    assert Truth.TRUE.negate() is Truth.FALSE
    assert Truth.FALSE.negate() is Truth.TRUE


def test_is_null_recognises_only_null():
    assert is_null(NULL)
    assert not is_null(0)
    assert not is_null("")


def test_type_names_are_sql_shaped():
    assert type_name(NULL) == "null"
    assert type_name(True) == "boolean"
    assert type_name(3) == "integer"
    assert type_name(3.5) == "float"
    assert type_name("a") == "string"


def test_an_unmodelled_value_has_no_type_name():
    with pytest.raises(SqlTypeError, match="unmodelled"):
        type_name([1])
