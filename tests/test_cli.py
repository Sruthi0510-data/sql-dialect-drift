"""Tests for the command line and its four exit codes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdd.cli import BAD_INPUT, DIVERGED, OK, UNATTRIBUTED, main


def test_no_command_is_a_usage_error():
    with pytest.raises(SystemExit):
        main([])


def test_check_finds_divergence_and_exits_three(capsys):
    assert main(["check"]) == DIVERGED
    out = capsys.readouterr().out
    assert "parse everywhere" in out and "diverge" in out


def test_check_names_the_axis_for_each_query(capsys):
    main(["check"])
    assert "null_order_asc" in capsys.readouterr().out


def test_check_names_the_query_that_agrees(capsys):
    main(["check"])
    assert "agrees everywhere" in capsys.readouterr().out


def test_check_reports_the_worst_pair(capsys):
    main(["check"])
    assert "disagree on" in capsys.readouterr().out


def test_two_postgres_derived_warehouses_exit_zero(capsys):
    """The migration people worry about least is the one that is actually safe."""
    assert main(["check", "--dialect", "postgres", "--dialect", "redshift"]) == OK


def test_an_unknown_dialect_is_a_bad_input(capsys):
    assert main(["check", "--dialect", "duckdb"]) == BAD_INPUT
    assert "no such dialect" in capsys.readouterr().err


def test_explain_shows_every_warehouse(capsys):
    assert main(["explain", "top-balances"]) == DIVERGED
    out = capsys.readouterr().out
    assert "bigquery" in out and "postgres" in out


def test_explain_shows_the_sql_and_the_reason(capsys):
    main(["explain", "top-balances"])
    out = capsys.readouterr().out
    assert "ORDER BY" in out and "why it is in the suite" in out


def test_explain_of_an_agreeing_query_exits_zero(capsys):
    assert main(["explain", "top-balances-explicit-nulls"]) == OK
    assert "same answer" in capsys.readouterr().out


def test_explain_says_when_the_decisions_cannot_be_told_apart(capsys):
    assert main(["explain", "blank-region"]) == DIVERGED
    assert "cannot be told apart" in capsys.readouterr().out


def test_explain_says_when_two_decisions_act_together(capsys):
    assert main(["explain", "not-emea"]) == DIVERGED
    assert "two act together" in capsys.readouterr().out


def test_explain_of_an_unknown_query_is_a_bad_input(capsys):
    assert main(["explain", "no-such-query"]) == BAD_INPUT
    assert "no such query" in capsys.readouterr().err


def test_explain_narrowed_to_agreeing_warehouses_exits_zero():
    assert main(["explain", "top-balances", "--dialect", "postgres", "--dialect", "redshift"]) == OK


def test_confounded_lists_the_groups(capsys):
    assert main(["confounded"]) == OK
    out = capsys.readouterr().out
    assert "can tell apart" in out and "divide_by_zero" in out


def test_confounded_says_it_is_a_property_of_the_warehouses_chosen(capsys):
    main(["confounded"])
    assert "not of SQL" in capsys.readouterr().out


def test_confounded_on_two_identical_warehouses_finds_everything_confounded(capsys):
    """Narrowed to warehouses that agree on every axis, nothing is separable.

    Postgres and Redshift differ on no modelled decision, so every axis
    partitions them the same way, which is the degenerate case the grouping has
    to handle without claiming a finding.
    """
    assert main(["confounded", "--dialect", "postgres", "--dialect", "redshift"]) == OK
    assert "can tell apart" in capsys.readouterr().out


def test_confounded_reports_nothing_when_every_axis_separates(capsys):
    assert main(["confounded", "--dialect", "postgres", "--dialect", "mysql"]) == OK


def test_table_prints_the_fixture(capsys):
    assert main(["table"]) == OK
    out = capsys.readouterr().out
    assert "acct-01" in out and "NULL" in out


def test_json_prints_the_report(capsys):
    assert main(["json"]) == DIVERGED
    payload = json.loads(capsys.readouterr().out)
    assert payload["queries"] == len(payload["results"])


def test_json_writes_to_a_file(tmp_path: Path, capsys):
    out = tmp_path / "report.json"
    assert main(["json", "--out", str(out)]) == DIVERGED
    assert json.loads(out.read_text())["diverging"] > 0


def test_json_carries_the_confounded_groups(capsys):
    main(["json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["confounded_axes"]


def test_the_four_exit_codes_are_distinct():
    assert len({OK, BAD_INPUT, DIVERGED, UNATTRIBUTED}) == 4


def test_blinding_the_model_makes_it_admit_it_cannot_attribute(capsys):
    """The only honest way the tool has of showing what incompleteness looks like."""
    assert main(["check", "--blind", "null_order_asc"]) == UNATTRIBUTED
    assert "unattributable      2" in capsys.readouterr().out


def test_blinding_changes_one_query_from_explained_to_unattributed(capsys):
    assert main(["explain", "top-balances", "--blind", "null_order_asc"]) == UNATTRIBUTED
    assert "no modelled decision explains this split" in capsys.readouterr().out


def test_blinding_an_unknown_decision_is_a_bad_input(capsys):
    assert main(["check", "--blind", "nulls_first"]) == BAD_INPUT
    assert "no such decision" in capsys.readouterr().err


def test_blinding_the_confounded_partners_leaves_everything_separable(capsys):
    """Each confounded pair has one member; drop it and the other stands alone."""
    code = main(["confounded", "--blind", "divide_by_zero", "--blind", "empty_string_is_null"])
    assert code == OK
    assert "every modelled decision is distinguishable" in capsys.readouterr().out


def test_json_reports_the_unattributed_verdict_too(capsys):
    assert main(["json", "--blind", "null_order_asc"]) == UNATTRIBUTED


def test_the_table_command_needs_no_blind_flag():
    assert main(["table"]) == OK
