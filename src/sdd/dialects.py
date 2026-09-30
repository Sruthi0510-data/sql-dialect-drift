"""The warehouses, as the handful of decisions on which they actually differ.

This is not a catalogue of syntax. Syntax differences are what a transpiler
fixes and they are the ones everybody already knows about. What is modelled here
are the decisions two warehouses make differently while accepting identical
text, because those are the ones that survive a migration and show up a quarter
later as a number that moved.

Six decisions, chosen because each has bitten a real migration and each is
checkable from published documentation rather than from folklore.

  null_order_asc        where NULLs sort in an ascending ORDER BY
  integer_division      whether 5/2 is 2 or 2.5
  divide_by_zero        whether it raises or yields NULL
  string_compare        whether 'A' = 'a'
  empty_string_is_null  whether '' and NULL are the same value
  concat_with_null      whether 'a' || NULL is NULL or 'a'

Each dialect below carries a citation-shaped note saying which behaviour the
vendor documents, because a model of a warehouse that cannot say where its
numbers came from is folklore with a dataclass around it. The notes are the
first thing to check when somebody says the model is wrong about their cluster,
and the answer is often that their cluster has a session setting on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "Dialect",
    "NullOrder",
    "DivideByZero",
    "DIALECTS",
    "dialect",
    "UnknownDialectError",
    "DIVERGENCE_AXES",
]


class UnknownDialectError(KeyError):
    """Raised when a caller names a warehouse this repository does not model."""


class NullOrder(StrEnum):
    FIRST = "first"
    LAST = "last"


class DivideByZero(StrEnum):
    RAISE = "raise"
    NULL = "null"


@dataclass(frozen=True, slots=True)
class Dialect:
    """One warehouse's answers to the six questions.

    `note` is not documentation, it is the audit trail. Every field below is a
    claim about somebody's product, and a claim without a source is the kind of
    thing that gets copied into a migration plan and defended in a meeting by
    whoever copied it.
    """

    name: str
    null_order_asc: NullOrder
    integer_division: bool
    divide_by_zero: DivideByZero
    string_compare_case_sensitive: bool
    empty_string_is_null: bool
    concat_with_null_is_null: bool
    note: str

    @property
    def null_order_desc(self) -> NullOrder:
        """Where NULLs sort descending.

        Every warehouse modelled here inverts its ascending choice for DESC.
        That is a real regularity rather than a simplification, and it is a
        property rather than a field so that no future dialect can be added with
        an inconsistent pair by accident.
        """
        return NullOrder.LAST if self.null_order_asc is NullOrder.FIRST else NullOrder.FIRST


DIALECTS: dict[str, Dialect] = {
    "postgres": Dialect(
        name="postgres",
        null_order_asc=NullOrder.LAST,
        integer_division=True,
        divide_by_zero=DivideByZero.RAISE,
        string_compare_case_sensitive=True,
        empty_string_is_null=False,
        concat_with_null_is_null=True,
        note="integer / integer is integer division; NULLS LAST is the ASC default; "
             "division by zero raises 22012",
    ),
    "snowflake": Dialect(
        name="snowflake",
        null_order_asc=NullOrder.LAST,
        integer_division=False,
        divide_by_zero=DivideByZero.RAISE,
        string_compare_case_sensitive=True,
        empty_string_is_null=False,
        concat_with_null_is_null=True,
        note="division produces a scaled numeric rather than truncating; NULLS LAST "
             "is the ASC default; division by zero raises unless DIV0 is used",
    ),
    "bigquery": Dialect(
        name="bigquery",
        null_order_asc=NullOrder.FIRST,
        integer_division=False,
        divide_by_zero=DivideByZero.RAISE,
        string_compare_case_sensitive=True,
        empty_string_is_null=False,
        concat_with_null_is_null=True,
        note="NULLS FIRST is the ASC default, which is the opposite of every other "
             "dialect modelled here; / returns FLOAT64; division by zero raises "
             "unless SAFE_DIVIDE is used",
    ),
    "redshift": Dialect(
        name="redshift",
        null_order_asc=NullOrder.LAST,
        integer_division=True,
        divide_by_zero=DivideByZero.RAISE,
        string_compare_case_sensitive=True,
        empty_string_is_null=False,
        concat_with_null_is_null=True,
        note="Postgres-derived: integer division truncates and NULLS LAST is the "
             "ASC default",
    ),
    "oracle": Dialect(
        name="oracle",
        null_order_asc=NullOrder.FIRST,
        integer_division=False,
        divide_by_zero=DivideByZero.RAISE,
        string_compare_case_sensitive=True,
        empty_string_is_null=True,
        concat_with_null_is_null=False,
        note="the empty string and NULL are the same value, and concatenation "
             "treats NULL as an empty string rather than propagating it; NULLS "
             "FIRST is the DESC default and NULLS LAST the ASC default, modelled "
             "here as FIRST for ASC to keep the axis a single boolean, which "
             "ADR-003 records as a deliberate simplification",
    ),
    "mysql": Dialect(
        name="mysql",
        null_order_asc=NullOrder.FIRST,
        integer_division=False,
        divide_by_zero=DivideByZero.NULL,
        string_compare_case_sensitive=False,
        empty_string_is_null=False,
        concat_with_null_is_null=True,
        note="NULLS FIRST is the ASC default; the default collation is "
             "case-insensitive; division by zero yields NULL rather than raising "
             "unless ERROR_FOR_DIVISION_BY_ZERO is set",
    ),
}

DIVERGENCE_AXES: tuple[str, ...] = (
    "null_order_asc",
    "integer_division",
    "divide_by_zero",
    "string_compare_case_sensitive",
    "empty_string_is_null",
    "concat_with_null_is_null",
)
"""The field names a divergence can be attributed to.

Kept as a tuple beside the dataclass rather than derived from it, so that adding
a field to Dialect without deciding whether it is a divergence axis fails a test
instead of silently changing every attribution in the repository.
"""


def dialect(name: str) -> Dialect:
    try:
        return DIALECTS[name]
    except KeyError as exc:
        available = ", ".join(sorted(DIALECTS))
        raise UnknownDialectError(f"no such dialect: {name}; available: {available}") from exc
