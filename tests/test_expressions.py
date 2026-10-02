"""Tests for the evaluator, one per divergence the model claims to produce."""

from __future__ import annotations

import pytest

from sdd.dialects import dialect
from sdd.expressions import (
    Binary,
    Column,
    Concat,
    DivisionByZero,
    IsNull,
    Literal,
    Not,
    NullIf,
    evaluate,
)
from sdd.values import NULL, SqlTypeError

PG = dialect("postgres")
BQ = dialect("bigquery")
MY = dialect("mysql")
ORA = dialect("oracle")


def test_a_literal_evaluates_to_itself():
    assert Literal(4).evaluate({}, PG) == 4


def test_an_empty_string_literal_is_null_on_oracle_only():
    assert Literal("").evaluate({}, ORA) is NULL
    assert Literal("").evaluate({}, PG) == ""


def test_a_non_string_zero_is_not_affected_by_the_oracle_rule():
    """`value == ""` is true for 0 in Python, so the rule checks the type too."""
    assert Literal(0).evaluate({}, ORA) == 0


def test_a_column_reads_from_the_row():
    assert Column("a").evaluate({"a": 7}, PG) == 7


def test_a_missing_column_is_an_error():
    with pytest.raises(SqlTypeError, match="no such column"):
        Column("nope").evaluate({"a": 1}, PG)


def test_an_empty_string_column_is_null_on_oracle():
    assert Column("a").evaluate({"a": ""}, ORA) is NULL
    assert Column("a").evaluate({"a": ""}, PG) == ""


def test_a_numeric_column_is_untouched_by_the_oracle_rule():
    assert Column("a").evaluate({"a": 0}, ORA) == 0


def test_an_unmodelled_operator_is_refused():
    with pytest.raises(SqlTypeError, match="unmodelled operator"):
        Binary("%", Literal(1), Literal(2))


def test_arithmetic_with_null_is_null():
    assert Binary("+", Literal(1), Literal(NULL)).evaluate({}, PG) is NULL
    assert Binary("+", Literal(NULL), Literal(1)).evaluate({}, PG) is NULL


def test_addition_subtraction_and_multiplication():
    assert Binary("+", Literal(2), Literal(3)).evaluate({}, PG) == 5
    assert Binary("-", Literal(2), Literal(3)).evaluate({}, PG) == -1
    assert Binary("*", Literal(2), Literal(3)).evaluate({}, PG) == 6


def test_arithmetic_on_a_string_is_an_error():
    with pytest.raises(SqlTypeError, match="cannot apply"):
        Binary("+", Literal("a"), Literal(1)).evaluate({}, PG)


def test_integer_division_truncates_on_postgres():
    assert Binary("/", Literal(5), Literal(2)).evaluate({}, PG) == 2


def test_the_same_division_is_exact_on_bigquery():
    assert Binary("/", Literal(5), Literal(2)).evaluate({}, BQ) == 2.5


def test_integer_division_truncates_towards_zero_not_floor():
    """Python floors; the C-derived engines truncate, and negatives separate them."""
    assert Binary("/", Literal(-7), Literal(2)).evaluate({}, PG) == -3
    assert Binary("/", Literal(7), Literal(-2)).evaluate({}, PG) == -3


def test_a_float_operand_defeats_integer_division():
    assert Binary("/", Literal(5.0), Literal(2)).evaluate({}, PG) == 2.5


def test_division_by_zero_raises_on_postgres():
    with pytest.raises(DivisionByZero):
        Binary("/", Literal(1), Literal(0)).evaluate({}, PG)


def test_the_error_message_does_not_name_the_dialect():
    """Naming it split five identical behaviours into five answers."""
    with pytest.raises(DivisionByZero) as caught:
        Binary("/", Literal(1), Literal(0)).evaluate({}, PG)
    assert "postgres" not in str(caught.value)


def test_division_by_zero_yields_null_on_mysql():
    assert Binary("/", Literal(1), Literal(0)).evaluate({}, MY) is NULL


def test_string_equality_is_case_sensitive_on_postgres():
    assert Binary("=", Literal("A"), Literal("a")).evaluate({}, PG) is False


def test_string_equality_is_case_insensitive_on_mysql():
    assert Binary("=", Literal("A"), Literal("a")).evaluate({}, MY) is True


def test_inequality_is_the_negation_of_equality():
    assert Binary("<>", Literal("A"), Literal("a")).evaluate({}, MY) is False
    assert Binary("<>", Literal("A"), Literal("a")).evaluate({}, PG) is True


def test_numeric_ordering_comparisons():
    for op, expected in (("<", True), ("<=", True), (">", False), (">=", False)):
        assert Binary(op, Literal(1), Literal(2)).evaluate({}, PG) is expected


def test_string_ordering_folds_case_on_mysql():
    assert Binary("<", Literal("B"), Literal("a")).evaluate({}, PG) is True
    assert Binary("<", Literal("B"), Literal("a")).evaluate({}, MY) is False


def test_comparing_a_string_with_a_number_is_an_error():
    with pytest.raises(SqlTypeError, match="cannot compare"):
        Binary("=", Literal("a"), Literal(1)).evaluate({}, PG)


def test_ordering_a_string_against_a_number_is_an_error():
    with pytest.raises(SqlTypeError, match="cannot compare"):
        Binary("<", Literal("a"), Literal(1)).evaluate({}, PG)


def test_a_comparison_with_null_is_null():
    assert Binary("=", Literal(1), Literal(NULL)).evaluate({}, PG) is NULL


def test_not_flips_a_boolean():
    assert Not(Literal(True)).evaluate({}, PG) is False
    assert Not(Literal(False)).evaluate({}, PG) is True


def test_not_null_is_null():
    assert Not(Literal(NULL)).evaluate({}, PG) is NULL


def test_is_null_is_never_unknown():
    assert IsNull(Literal(NULL)).evaluate({}, PG) is True
    assert IsNull(Literal(1)).evaluate({}, PG) is False


def test_is_null_is_true_for_an_empty_string_on_oracle():
    """The divergence that turns a data-quality check into a no-op."""
    assert IsNull(Literal("")).evaluate({}, ORA) is True
    assert IsNull(Literal("")).evaluate({}, PG) is False


def test_nullif_nulls_a_matching_value():
    assert NullIf(Literal(0), Literal(0)).evaluate({}, PG) is NULL


def test_nullif_passes_a_non_matching_value():
    assert NullIf(Literal(3), Literal(0)).evaluate({}, PG) == 3


def test_nullif_passes_null_through():
    assert NullIf(Literal(NULL), Literal(0)).evaluate({}, PG) is NULL


def test_nullif_with_a_null_sentinel_changes_nothing():
    assert NullIf(Literal(3), Literal(NULL)).evaluate({}, PG) == 3


def test_nullif_uses_the_dialect_collation():
    assert NullIf(Literal("EMEA"), Literal("emea")).evaluate({}, MY) is NULL
    assert NullIf(Literal("EMEA"), Literal("emea")).evaluate({}, PG) == "EMEA"


def test_nullif_removes_the_divide_by_zero_and_leaves_the_division_rule():
    guarded = Binary("/", Literal(5), NullIf(Literal(0), Literal(0)))
    assert guarded.evaluate({}, PG) is NULL
    assert Binary("/", Literal(5), NullIf(Literal(2), Literal(0))).evaluate({}, PG) == 2


def test_concat_joins_parts():
    assert Concat((Literal("a"), Literal("b"))).evaluate({}, PG) == "ab"


def test_concat_renders_a_number():
    assert Concat((Literal("a"), Literal(1))).evaluate({}, PG) == "a1"


def test_concat_with_null_is_null_on_postgres():
    assert Concat((Literal("a"), Literal(NULL))).evaluate({}, PG) is NULL


def test_concat_ignores_null_on_oracle():
    assert Concat((Literal("a"), Literal(NULL))).evaluate({}, ORA) == "a"


def test_concat_of_nothing_is_the_empty_string():
    assert Concat(()).evaluate({}, PG) == ""


def test_evaluate_is_a_thin_alias():
    assert evaluate(Literal(1), {}, PG) == 1


def test_ordering_two_values_the_model_cannot_rank_is_an_error():
    """Two values of the same unmodelled kind pass the string check and reach the ranker."""
    with pytest.raises(SqlTypeError, match="cannot compare"):
        Binary("<", Literal([1]), Literal([2])).evaluate({}, PG)


def test_the_comparison_error_does_not_raise_from_inside_its_own_message():
    """Building the message with type_name raised a second, useless error."""
    with pytest.raises(SqlTypeError) as caught:
        Binary("<", Literal([1]), Literal([2])).evaluate({}, PG)
    assert "cannot compare" in str(caught.value)
