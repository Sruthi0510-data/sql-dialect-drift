"""Tests for sorting and for the query suite's own claims about itself."""

from __future__ import annotations

import pytest

from sdd.dialects import NullOrder, dialect
from sdd.expressions import Column, Literal
from sdd.ordering import SortKey, order_rows, sort_positions
from sdd.queries import SUITE, UnknownQueryError, query
from sdd.values import NULL, SqlTypeError

PG = dialect("postgres")
BQ = dialect("bigquery")
MY = dialect("mysql")


def sample():
    return [
        {"account": "a", "v": 2},
        {"account": "b", "v": NULL},
        {"account": "c", "v": 1},
    ]


def test_sorting_nothing_gives_nothing():
    assert order_rows([], [SortKey(Column("v"))], PG) == ()


def test_sorting_with_no_keys_preserves_input_order():
    rows = sample()
    assert order_rows(rows, [], PG) == tuple(rows)


def test_postgres_puts_nulls_last_ascending():
    assert sort_positions(sample(), [SortKey(Column("v"))], PG, "account") == ("c", "a", "b")


def test_bigquery_puts_nulls_first_ascending():
    assert sort_positions(sample(), [SortKey(Column("v"))], BQ, "account") == ("b", "c", "a")


def test_descending_inverts_the_null_placement():
    key = [SortKey(Column("v"), descending=True)]
    assert sort_positions(sample(), key, PG, "account") == ("b", "a", "c")
    assert sort_positions(sample(), key, BQ, "account") == ("a", "c", "b")


def test_an_explicit_placement_overrides_the_dialect():
    """One clause, and the whole family of divergences is gone."""
    key = [SortKey(Column("v"), nulls=NullOrder.LAST)]
    assert sort_positions(sample(), key, PG, "account") == sort_positions(sample(), key, BQ, "account")


def test_an_explicit_placement_works_descending_too():
    key = [SortKey(Column("v"), descending=True, nulls=NullOrder.FIRST)]
    assert sort_positions(sample(), key, PG, "account") == sort_positions(sample(), key, BQ, "account")


def test_a_second_key_breaks_ties_in_the_first():
    rows = [
        {"account": "b", "v": 1},
        {"account": "a", "v": 1},
    ]
    keys = [SortKey(Column("v")), SortKey(Column("account"))]
    assert sort_positions(rows, keys, PG, "account") == ("a", "b")


def test_string_sorting_folds_case_on_mysql():
    rows = [{"account": "x", "v": "B"}, {"account": "y", "v": "a"}]
    keys = [SortKey(Column("v"))]
    assert sort_positions(rows, keys, PG, "account") == ("x", "y")
    assert sort_positions(rows, keys, MY, "account") == ("y", "x")


def test_booleans_sort_as_numbers():
    rows = [{"account": "t", "v": True}, {"account": "f", "v": False}]
    assert sort_positions(rows, [SortKey(Column("v"))], PG, "account") == ("f", "t")


def test_a_missing_projected_column_reads_as_null():
    rows = [{"v": 1}]
    assert sort_positions(rows, [SortKey(Column("v"))], PG, "account") == (NULL,)


def test_sorting_an_unsortable_value_is_an_error():
    rows = [{"account": "a", "v": [1]}, {"account": "b", "v": 2}]
    with pytest.raises(SqlTypeError, match="cannot sort"):
        order_rows(rows, [SortKey(Column("v"))], PG)


def test_the_suite_has_a_query_of_each_shape():
    from sdd.queries import Filter, Ordered, Project

    shapes = {type(item) for item in SUITE}
    assert shapes == {Filter, Ordered, Project}


def test_every_query_name_is_unique():
    names = [item.name for item in SUITE]
    assert len(set(names)) == len(names)


def test_every_query_carries_sql_and_a_reason():
    assert all(item.sql.strip() and item.why.strip() for item in SUITE)


def test_every_query_declares_a_modelled_axis_or_none():
    from sdd.dialects import DIVERGENCE_AXES

    assert all(item.axis in set(DIVERGENCE_AXES) | {"none"} for item in SUITE)


def test_exactly_one_query_claims_to_agree_everywhere():
    """The fix, priced. If a second appears, the suite has stopped being a suite."""
    assert [item.name for item in SUITE if item.axis == "none"] == [
        "top-balances-explicit-nulls"
    ]


def test_looking_up_a_query_by_name_works():
    assert query("half-balance").name == "half-balance"


def test_an_unknown_query_lists_the_known_ones():
    with pytest.raises(UnknownQueryError, match="available: blank-region"):
        query("no-such-query")


def test_a_filter_reports_membership_rather_than_a_count():
    """A count that matches while the membership differs is the failure that survives review."""
    from sdd.queries import Filter

    filters = [item for item in SUITE if isinstance(item, Filter)]
    rows = [{"account": "a", "region": "emea"}, {"account": "b", "region": "apac"}]
    answer = filters[0].answer(rows, PG)
    assert all(isinstance(value, str) for value in answer)
