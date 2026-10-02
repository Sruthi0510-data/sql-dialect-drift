"""The fixture table, small enough to reason about by hand.

Twelve rows. Every row exists to make one specific divergence reachable, and the
docstring on each field says which, because a fixture whose rows are there for
no stated reason is a fixture that gets trimmed by somebody tidying up and takes
half the findings with it.

Small by design. A thousand rows would make the same point and no reader would
check it, and the whole value of this repository is that a sceptic can verify a
finding with a pencil.
"""

from __future__ import annotations

from typing import Any

from sdd.values import NULL, Value

__all__ = ["COLUMNS", "ROWS", "rows_as_dicts"]

COLUMNS: tuple[str, ...] = ("account", "region", "balance_cents", "settled_cents", "note")

ROWS: tuple[tuple[Any, ...], ...] = (
    # An ordinary row, so that "everything diverges" is visibly false.
    ("acct-01", "emea", 5_000, 2_500, "standard"),
    # A NULL sort key: the row that lands first on BigQuery and last on Postgres.
    ("acct-02", "emea", NULL, 1_000, "awaiting settlement"),
    # A second NULL, so the divergence is a block rather than a single row and a
    # LIMIT 2 is enough to show it.
    ("acct-03", "apac", NULL, 0, "awaiting settlement"),
    # An odd numerator over an even denominator: 2 on Postgres, 2.5 elsewhere.
    ("acct-04", "apac", 5, 2, "rounding"),
    # A negative numerator, which separates truncation from floor division.
    ("acct-05", "amer", -7, 2, "rounding"),
    # A zero denominator: an error on five dialects and a NULL on MySQL.
    ("acct-06", "amer", 100, 0, "unsettled"),
    # Case differing only in capitals: equal on MySQL, unequal everywhere else.
    ("acct-07", "EMEA", 250, 250, "case"),
    # The empty string: NULL on Oracle and a value everywhere else.
    ("acct-08", "", 300, 300, ""),
    # A NULL in a concatenated field: absorbing on five dialects, ignored on Oracle.
    ("acct-09", "apac", 400, 400, NULL),
    # Equal balances that must not create a tie the suite depends on, so the
    # accounts differ and every query orders by account as its final key.
    ("acct-10", "emea", 5_000, 5_000, "settled"),
    ("acct-11", "amer", 1, 3, "rounding"),
    ("acct-12", "apac", 0, 0, "zero"),
)


def rows_as_dicts() -> tuple[dict[str, Value], ...]:
    return tuple(dict(zip(COLUMNS, row, strict=True)) for row in ROWS)
