"""ORDER BY, where the divergence is invisible until somebody takes the top row.

Sorting is the divergence people discount. Two warehouses returning the same set
of rows in a different order feels cosmetic, and it is, right up until a query
says LIMIT 1, or a report shows the first page, or a downstream job takes the
head of the file. Then the order is the answer.

The specific trap modelled here is NULL placement. Ascending, most engines put
NULLs last and BigQuery puts them first. A query that ranks customers by last
order date and takes the top ten returns ten real customers on one warehouse and
ten customers who have never ordered on another, with no error anywhere.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sdd.dialects import Dialect, NullOrder
from sdd.expressions import Expression, Row
from sdd.values import NULL, SqlTypeError, Value, is_null

__all__ = ["SortKey", "order_rows", "sort_positions"]


@dataclass(frozen=True, slots=True)
class SortKey:
    """One ORDER BY term.

    `nulls` overrides the dialect default when a query has written it out. That
    is the fix for the whole family of divergences, and modelling it lets the
    experiments measure what writing it costs, which is nothing, against what
    omitting it costs, which is the headline.
    """

    expression: Expression
    descending: bool = False
    nulls: NullOrder | None = None

    def placement(self, dialect: Dialect) -> NullOrder:
        if self.nulls is not None:
            return self.nulls
        return dialect.null_order_desc if self.descending else dialect.null_order_asc


def _sortable(value: Value) -> Value:
    """A sortable surrogate for a non-null value.

    Never sees a NULL. An earlier version returned a (null_flag, payload) pair
    so that NULLs could be sorted alongside real values, and branch coverage
    showed the null branch was unreachable: `order_rows` partitions the NULLs
    out before it sorts anything, because a comparison between NULL and a value
    is something SQL has no answer for either. The pair was machinery for a case
    that could not arrive, so it is gone.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    # Not `type_name(value)`. That helper raises on a value it cannot name, so
    # building this message with it replaced a clear "cannot sort" with an
    # obscure "unmodelled value" raised from inside the error path, which is the
    # worst possible moment to raise a second error.
    raise SqlTypeError(f"cannot sort {value!r}")


def order_rows(
    rows: Sequence[Row], keys: Sequence[SortKey], dialect: Dialect
) -> tuple[Row, ...]:
    """Sort rows the way one dialect would.

    Keys are applied in reverse so that Python's stable sort produces the same
    result as a multi-key comparison, which is the standard idiom and the one
    place in this file where a reader should check the code rather than trust
    the docstring.

    Ties beyond the last key keep input order. Real warehouses do not promise
    that and neither does this function's contract; ADR-002 records why the
    repository refuses to measure divergences that come from unspecified tie
    order, and the suite avoids constructing them.
    """
    ordered = list(rows)
    for key in reversed(keys):
        nulls_first = key.placement(dialect) is NullOrder.FIRST

        def sort_key(row: Row, key: SortKey = key):
            payload = _sortable(key.expression.evaluate(row, dialect))
            if isinstance(payload, str) and not dialect.string_compare_case_sensitive:
                return payload.casefold()
            return payload

        non_null = [row for row in ordered if not is_null(key.expression.evaluate(row, dialect))]
        nulls = [row for row in ordered if is_null(key.expression.evaluate(row, dialect))]
        non_null.sort(key=sort_key, reverse=key.descending)
        ordered = nulls + non_null if nulls_first else non_null + nulls
    return tuple(ordered)


def sort_positions(
    rows: Sequence[Row], keys: Sequence[SortKey], dialect: Dialect, column: str
) -> tuple[Value, ...]:
    """The values of one column in sorted order, which is what a diff compares.

    Comparing whole rows would report a divergence whenever a row carries a
    column nobody selected, so the comparison is over the projected column only.
    """
    return tuple(row.get(column, NULL) for row in order_rows(rows, keys, dialect))
