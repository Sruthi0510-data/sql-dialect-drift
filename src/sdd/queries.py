"""The queries, and the three shapes they come in.

Every query here is one a person would write without thinking twice, and every
one of them is accepted by all six warehouses. That is the premise: a transpiler
handed any of these returns valid target SQL and reports success. The suite
exists to ask the question the transpiler cannot, which is whether the answer is
the same.

Three shapes, because they are the three ways a divergence reaches a consumer.

  Project  a computed column lands in a table somebody reads
  Filter   a predicate decides which rows exist at all
  Ordered  a ranking decides which rows are on the first page

Each query names the axis it exercises. The naming is checked against the
measured divergences by a test: a query whose declared axis does not match the
dialects that actually disagree is a query whose author was wrong about why it
diverges, and that is worth failing a build over.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sdd.dialects import Dialect, NullOrder
from sdd.expressions import Binary, Column, Concat, Expression, IsNull, Literal, NullIf, Row
from sdd.ordering import SortKey, order_rows
from sdd.values import NULL, Value, truth_of

__all__ = ["Query", "Project", "Filter", "Ordered", "SUITE", "query", "UnknownQueryError"]


class UnknownQueryError(KeyError):
    """Raised when a caller names a query the suite does not contain."""


@dataclass(frozen=True, slots=True)
class Project:
    """A computed column, evaluated for every row in fixture order."""

    name: str
    sql: str
    axis: str
    expression: Expression
    why: str

    def answer(self, rows: Sequence[Row], dialect: Dialect) -> tuple[Value, ...]:
        return tuple(self.expression.evaluate(row, dialect) for row in rows)


@dataclass(frozen=True, slots=True)
class Filter:
    """A predicate, reported as the accounts it keeps.

    Reported as the surviving keys rather than as a count, because a count that
    matches while the membership differs is the failure mode that survives
    review, and a diff over counts would call it identical.
    """

    name: str
    sql: str
    axis: str
    predicate: Expression
    why: str

    def answer(self, rows: Sequence[Row], dialect: Dialect) -> tuple[Value, ...]:
        return tuple(
            row["account"]
            for row in rows
            if truth_of(self.predicate.evaluate(row, dialect)).keeps_row()
        )


@dataclass(frozen=True, slots=True)
class Ordered:
    """A ranking, reported as the first `limit` accounts.

    The limit is what makes an ordering divergence observable rather than
    cosmetic, and it is also what a real report does.
    """

    name: str
    sql: str
    axis: str
    keys: tuple[SortKey, ...]
    limit: int
    why: str

    def answer(self, rows: Sequence[Row], dialect: Dialect) -> tuple[Value, ...]:
        ordered = order_rows(rows, self.keys, dialect)
        return tuple(row["account"] for row in ordered[: self.limit])


Query = Project | Filter | Ordered

_ACCOUNT = Column("account")

SUITE: tuple[Query, ...] = (
    Ordered(
        name="top-balances",
        sql="SELECT account FROM ledger ORDER BY balance_cents, account LIMIT 3",
        axis="null_order_asc",
        keys=(SortKey(Column("balance_cents")), SortKey(_ACCOUNT)),
        limit=3,
        why="the first page of a ranking, which is what a report shows and a "
            "downstream job takes the head of",
    ),
    Ordered(
        name="largest-balances",
        sql="SELECT account FROM ledger ORDER BY balance_cents DESC, account LIMIT 3",
        axis="null_order_asc",
        keys=(SortKey(Column("balance_cents"), descending=True), SortKey(_ACCOUNT)),
        limit=3,
        why="the same ranking the other way up, because a reader who has seen the "
            "ascending case assumes descending is safe",
    ),
    Ordered(
        name="top-balances-explicit-nulls",
        sql="SELECT account FROM ledger ORDER BY balance_cents NULLS LAST, account LIMIT 3",
        axis="none",
        keys=(SortKey(Column("balance_cents"), nulls=NullOrder.LAST), SortKey(_ACCOUNT)),
        limit=3,
        why="the fix, written out, so the repository can price it: one clause, and "
            "the divergence is gone",
    ),
    Project(
        name="settled-ratio",
        sql="SELECT balance_cents / settled_cents FROM ledger",
        axis="divide_by_zero",
        expression=Binary("/", Column("balance_cents"), Column("settled_cents")),
        why="a ratio over a column that contains a zero. Five warehouses raise and "
            "one returns NULL, and the raise hides the integer-division "
            "divergence underneath it: a query that fails everywhere it would "
            "have disagreed looks like a query with one problem",
    ),
    Project(
        name="half-balance",
        sql="SELECT balance_cents / 2 FROM ledger",
        axis="integer_division",
        expression=Binary("/", Column("balance_cents"), Literal(2)),
        why="division by a literal, where the truncation is easiest to miss "
            "because the denominator looks harmless",
    ),
    Project(
        name="ratio-guarded",
        sql="SELECT balance_cents / NULLIF(settled_cents, 0) FROM ledger",
        axis="integer_division",
        expression=Binary(
            "/", Column("balance_cents"), NullIf(Column("settled_cents"), Literal(0))
        ),
        why="the same ratio with the zero guarded, which removes one axis and "
            "leaves the other, so a reader can see that guarding is not a fix "
            "for the thing it is usually assumed to fix",
    ),
    Filter(
        name="not-emea",
        sql="SELECT account FROM ledger WHERE region <> 'emea'",
        axis="string_compare_case_sensitive",
        predicate=Binary("<>", Column("region"), Literal("emea")),
        why="an exclusion filter, which on a case-insensitive collation quietly "
            "drops a row that the query author meant to keep",
    ),
    Filter(
        name="region-is-emea",
        sql="SELECT account FROM ledger WHERE region = 'emea'",
        axis="string_compare_case_sensitive",
        predicate=Binary("=", Column("region"), Literal("emea")),
        why="the same comparison the other way round, because a team that checks "
            "one usually assumes the other follows",
    ),
    Filter(
        name="blank-region",
        sql="SELECT account FROM ledger WHERE region = ''",
        axis="empty_string_is_null",
        predicate=Binary("=", Column("region"), Literal("")),
        why="the data-quality check that becomes a no-op on a warehouse where the "
            "empty string is NULL",
    ),
    Filter(
        name="region-is-null",
        sql="SELECT account FROM ledger WHERE region IS NULL",
        axis="empty_string_is_null",
        predicate=IsNull(Column("region")),
        why="the other half of the same check, which gains a row on exactly the "
            "warehouse where the first one loses it",
    ),
    Project(
        name="label",
        sql="SELECT account || ' ' || note FROM ledger",
        axis="concat_with_null_is_null",
        expression=Concat((Column("account"), Literal(" "), Column("note"))),
        why="a concatenated label, which is either NULL or a usable string "
            "depending on whether the warehouse thinks NULL is absorbing",
    ),
)


def query(name: str) -> Query:
    for candidate in SUITE:
        if candidate.name == name:
            return candidate
    available = ", ".join(sorted(item.name for item in SUITE))
    raise UnknownQueryError(f"no such query: {name}; available: {available}")
