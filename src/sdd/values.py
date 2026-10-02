"""The value model, and the one decision that makes the rest of the repository possible.

SQL values are not Python values. The difference that matters is NULL, which is
neither a value nor an absence but a third thing that propagates through
arithmetic, poisons comparisons into a third truth value, and then is treated as
ordinary data by ORDER BY and GROUP BY. Modelling it as Python's None and
relying on Python's operators produces a model that is wrong in exactly the
places the interesting divergences live.

So values here are tagged. `Null` is a singleton with no ordering and no
arithmetic of its own, and every operation that could meet it says what it does.
Three-valued logic is explicit: `Unknown` is a distinct truth value, not a
falsy None, because a WHERE clause keeps rows where the predicate is TRUE and
discards both FALSE and UNKNOWN, while a CHECK constraint accepts TRUE and
UNKNOWN and rejects only FALSE. Collapsing them hides half the divergences.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "NULL",
    "NullType",
    "Truth",
    "Value",
    "SqlTypeError",
    "is_null",
    "truth_of",
    "type_name",
]


class SqlTypeError(TypeError):
    """Raised when an operation has no defined meaning on the values it was given.

    Distinct from a dialect disagreement. A disagreement is two warehouses
    answering differently; this is nobody having an answer, and the evaluator
    reports it rather than inventing one.
    """


class NullType:
    """The SQL NULL, as a singleton with no useful behaviour of its own.

    Deliberately not None. Code that reaches for `if value:` on a NULL gets a
    truthy object and a bug; code that reaches for `value is NULL` gets the right
    answer. Making the wrong idiom fail loudly is worth one class.
    """

    _instance: NullType | None = None

    def __new__(cls) -> NullType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NULL"

    def __bool__(self) -> bool:
        raise SqlTypeError("NULL has no truth value; use truth_of")


NULL = NullType()

Value = int | float | str | bool | NullType


class Truth(Enum):
    """SQL's three truth values, kept apart because the difference is load bearing.

    A WHERE clause keeps TRUE and discards FALSE and UNKNOWN alike, which is why
    `WHERE x <> 'a'` silently drops the rows where x is NULL. A CHECK constraint
    accepts TRUE and UNKNOWN and rejects only FALSE, which is why the same
    predicate written as a constraint lets those rows through. Both behaviours
    are in this repository and they would be indistinguishable if UNKNOWN were
    modelled as a falsy None.
    """

    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def keeps_row(self) -> bool:
        return self is Truth.TRUE

    def passes_constraint(self) -> bool:
        return self is not Truth.FALSE

    def negate(self) -> Truth:
        if self is Truth.TRUE:
            return Truth.FALSE
        if self is Truth.FALSE:
            return Truth.TRUE
        return Truth.UNKNOWN


def is_null(value: Value) -> bool:
    return value is NULL


def truth_of(value: Value) -> Truth:
    """Read a value as a truth value.

    NULL becomes UNKNOWN rather than FALSE, which is the whole point. A number
    is truthy when non-zero, which is what the dialects that allow it agree on;
    the ones that do not allow it never produce a number here.
    """
    if value is NULL:
        return Truth.UNKNOWN
    if isinstance(value, bool):
        return Truth.TRUE if value else Truth.FALSE
    if isinstance(value, (int, float)):
        return Truth.TRUE if value != 0 else Truth.FALSE
    raise SqlTypeError(f"no truth value for {type_name(value)}")


def type_name(value: Value) -> str:
    """The SQL-ish type name, for error messages a reader can act on."""
    if value is NULL:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    raise SqlTypeError(f"unmodelled value {value!r}")
