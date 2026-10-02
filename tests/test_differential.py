"""Tests for the runner and, above all, for the attribution.

The attribution is the part that turns a diff into something a migration plan
can act on, and it is also the part most likely to be confidently wrong, so most
of these tests are about the cases where it must refuse to name a cause.
"""

from __future__ import annotations

import pytest

from sdd.dialects import DIALECTS, dialect
from sdd.differential import (
    Answer,
    explain_jointly,
    explain_split,
    run_query,
    run_suite,
)
from sdd.expressions import Binary, Literal
from sdd.queries import SUITE, Project, query
from sdd.values import NULL

ALL = tuple(DIALECTS.values())


@pytest.fixture(scope="module")
def report():
    return run_suite(SUITE, ALL)


def test_every_query_in_the_suite_runs_on_every_warehouse(report):
    assert all(len(result.answers) == len(ALL) for result in report.results)


def test_every_query_parses_everywhere(report):
    """The premise: a transpiler handed any of these reports success."""
    assert all(not result.raises_everywhere for result in report.results)


def test_most_queries_diverge(report):
    assert report.divergence_share > 0.8


def test_the_explicit_nulls_query_is_the_one_that_agrees(report):
    agreeing = [result.query for result in report.results if not result.diverges]
    assert agreeing == ["top-balances-explicit-nulls"]


def test_no_divergence_is_left_unattributed(report):
    assert report.unexplained == ()


def test_every_query_declaration_survives_measurement(report):
    """A query whose declared axis is not among the measured ones was mislabelled."""
    wrong = [result.query for result in report.results if not result.declaration_holds]
    assert wrong == []


def test_one_query_needs_two_decisions_acting_together(report):
    assert len(report.needing_two_axes) == 1


def test_some_axes_cannot_be_told_apart_on_these_warehouses(report):
    """A property of the six chosen, not of SQL, and reported as one."""
    assert report.confounded_axes()


def test_confounded_axes_partition_the_warehouses_identically(report):
    for group in report.confounded_axes():
        partitions = {
            frozenset(
                frozenset(
                    name
                    for name in report.dialects
                    if getattr(DIALECTS[name], axis) == value
                )
                for value in {getattr(DIALECTS[n], axis) for n in report.dialects}
            )
            for axis in group
        }
        assert len(partitions) == 1


def test_a_confounded_result_names_every_candidate(report):
    confounded = [result for result in report.results if result.confounded]
    assert confounded and all(len(result.explained_by) > 1 for result in confounded)


def test_the_worst_pair_is_stable_and_real(report):
    left, right, count = report.worst_pair()
    assert left in report.dialects and right in report.dialects and left != right
    assert 0 < count <= len(report.results)


def test_two_postgres_derived_warehouses_agree_on_everything():
    """The migration people worry about least is the one that is actually safe."""
    narrow = run_suite(SUITE, [dialect("postgres"), dialect("redshift")])
    assert narrow.diverging == ()
    assert narrow.divergence_share == 0.0


def test_a_narrowed_run_can_still_diverge():
    narrow = run_suite(SUITE, [dialect("postgres"), dialect("bigquery")])
    assert narrow.diverging


def test_an_empty_suite_has_a_zero_divergence_share():
    assert run_suite([], ALL).divergence_share == 0.0


def test_an_error_is_recorded_as_an_answer():
    result = run_query(query("settled-ratio"), ALL)
    assert any(answer.failed for answer in result.answers)
    assert result.raises_somewhere


def test_warehouses_that_raise_for_the_same_reason_share_a_group():
    """The bug that split five identical behaviours into five answers."""
    result = run_query(query("settled-ratio"), ALL)
    failing = {answer.dialect for answer in result.answers if answer.failed}
    assert len(failing) > 1
    groups = [set(group) for group in result.groups]
    assert failing in groups


def test_an_answer_renders_nulls_as_null():
    assert Answer(dialect="x", values=(NULL, 1)).rendered() == "NULL, 1"


def test_an_answer_renders_its_error():
    assert Answer(dialect="x", values=None, error="boom").rendered() == "error: boom"


def test_axis_counts_cover_every_axis(report):
    from sdd.dialects import DIVERGENCE_AXES

    assert set(report.axis_counts()) == set(DIVERGENCE_AXES)


def test_explain_split_finds_nothing_for_an_impossible_partition():
    """A split the model cannot produce is reported as unexplained, not guessed at."""
    groups = [("postgres",), ("snowflake",), ("bigquery", "redshift", "oracle", "mysql")]
    assert explain_split(groups, tuple(DIALECTS)) == ()


def test_explain_jointly_finds_nothing_for_an_impossible_partition():
    groups = [("postgres",), ("snowflake",), ("bigquery", "redshift", "oracle", "mysql")]
    assert explain_jointly(groups, tuple(DIALECTS)) == ()


def test_a_query_whose_split_no_decision_explains_is_unattributed():
    """Synthesised deliberately: the model admitting its own limits is a feature."""

    class OddOne:
        name = "synthetic"
        sql = "SELECT 1"
        axis = "none"
        why = "a synthetic split no modelled decision produces"

        def answer(self, rows, dialect):
            return (0,) if dialect.name in {"postgres", "snowflake"} else (1,)

    result = run_query(OddOne(), ALL)
    assert result.diverges and result.unexplained
    assert not result.declaration_holds


def test_a_non_diverging_query_declaring_an_axis_fails_its_declaration():
    constant = Project(
        name="constant",
        sql="SELECT 1",
        axis="integer_division",
        expression=Literal(1),
        why="a query that cannot diverge but claims an axis",
    )
    assert not run_query(constant, ALL).declaration_holds


def test_a_divergence_the_model_explains_is_not_unexplained():
    ratio = Project(
        name="ratio",
        sql="SELECT 5 / 2",
        axis="integer_division",
        expression=Binary("/", Literal(5), Literal(2)),
        why="the simplest possible integer division",
    )
    result = run_query(ratio, ALL)
    assert result.explained_by == ("integer_division",)
    assert not result.needs_two_axes


def test_running_the_suite_with_no_dialects_given_uses_all_of_them():
    assert len(run_suite(SUITE).dialects) == len(DIALECTS)


def test_the_report_lists_its_confounded_results(report):
    names = {result.query for result in report.confounded}
    assert names and names <= {result.query for result in report.diverging}
