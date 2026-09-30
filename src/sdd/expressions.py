"""A small expression language, and per-dialect evaluation of it.

Not a SQL parser. A parser would be a large amount of code in service of a point
this repository makes with six operators, and every line of it would be a place
for a reader to lose the argument. Queries here are built as expression trees,
which is what a transpiler works on anyway once its own parser has run.

What the evaluator does that a transpiler does not is carry a dialect. The same
tree evaluated under two dialects can produce two answers, and the whole
repository is the set of trees for which it does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from sdd.dialects import Dialect, DivideByZero
from sdd.values import NULL, SqlTypeError, Truth, Value, is_null, truth_of, type_name

__all__ = [
    "Expression",
    "Literal",
    "Column",
    "Binary",
    "Not",
    "IsNull",
    "NullIf",
    "Concat",
    "Row",
    "DivisionByZero",
    "evaluate",
]

Row = Mapping[str, Value]


class DivisionByZero(ArithmeticError):
    """Raised when a dialect that raises on division by zero is asked to divide by zero.

    A real error from a modelled warehouse, not a bug in the model. The runner
    catches it and records it as that dialect's answer, because "this query
    fails here and returns a number there" is the most expensive kind of
    divergence and deserves to be in the table rather than crashing the run.
    """


class Expression(Protocol):
    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        ...  # pragma: no cover


@dataclass(frozen=True, slots=True)
class Literal:
    value: Value

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        """Read a literal, applying the dialect's view of the empty string.

        Oracle stores the empty string as NULL, which means a literal '' in a
        query means something different there before any operator has run. The
        conversion happens here rather than at comparison time so that every
        downstream operator sees the value the warehouse would actually have.
        """
        if dialect.empty_string_is_null and self.value == "" and isinstance(self.value, str):
            return NULL
        return self.value


@dataclass(frozen=True, slots=True)
class Column:
    name: str

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        if self.name not in row:
            raise SqlTypeError(f"no such column: {self.name}")
        value = row[self.name]
        if dialect.empty_string_is_null and value == "" and isinstance(value, str):
            return NULL
        return value


def _compare_strings(left: str, right: str, dialect: Dialect) -> bool:
    if dialect.string_compare_case_sensitive:
        return left == right
    return left.casefold() == right.casefold()


def _order_key(left: Value, right: Value, dialect: Dialect) -> int:
    if isinstance(left, str) and isinstance(right, str):
        if not dialect.string_compare_case_sensitive:
            left, right = left.casefold(), right.casefold()
        return (left > right) - (left < right)
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return (left > right) - (left < right)
    # Rendered with repr rather than type_name for the same reason the sort does:
    # type_name raises on a value it cannot name, so using it here replaced a
    # clear "cannot compare" with an obscure error raised from inside the error
    # path. Branch coverage found both occurrences on the same afternoon.
    raise SqlTypeError(f"cannot compare {left!r} with {right!r}")


@dataclass(frozen=True, slots=True)
class Binary:
    """One binary operator, evaluated under a dialect.

    The operator set is small on purpose: the four arithmetic operators and the
    six comparisons are enough to express every divergence this repository
    measures, and a larger set would add code without adding an argument.
    """

    op: str
    left: Expression
    right: Expression

    ARITHMETIC = frozenset({"+", "-", "*", "/"})
    COMPARISON = frozenset({"=", "<>", "<", "<=", ">", ">="})

    def __post_init__(self) -> None:
        if self.op not in self.ARITHMETIC | self.COMPARISON:
            raise SqlTypeError(f"unmodelled operator: {self.op}")

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        left = self.left.evaluate(row, dialect)
        right = self.right.evaluate(row, dialect)
        if is_null(left) or is_null(right):
            return NULL
        if self.op in self.ARITHMETIC:
            return self._arithmetic(left, right, dialect)
        return self._compare(left, right, dialect)

    def _arithmetic(self, left: Value, right: Value, dialect: Dialect) -> Value:
        if isinstance(left, str) or isinstance(right, str):
            raise SqlTypeError(f"cannot apply {self.op} to {type_name(left)}")
        if self.op == "+":
            return left + right
        if self.op == "-":
            return left - right
        if self.op == "*":
            return left * right
        if right == 0:
            if dialect.divide_by_zero is DivideByZero.NULL:
                return NULL
            raise DivisionByZero("division by zero")
        if dialect.integer_division and isinstance(left, int) and isinstance(right, int):
            # Truncation towards zero, which is what the C-derived engines do and
            # which differs from Python's floor for negative operands. Getting
            # this wrong would have made every negative-numerator case agree
            # when the warehouses do not.
            quotient = abs(left) // abs(right)
            return -quotient if (left < 0) != (right < 0) else quotient
        return left / right

    def _compare(self, left: Value, right: Value, dialect: Dialect) -> Value:
        if isinstance(left, str) != isinstance(right, str):
            raise SqlTypeError(f"cannot compare {type_name(left)} with {type_name(right)}")
        if self.op in {"=", "<>"}:
            equal = (
                _compare_strings(left, right, dialect)
                if isinstance(left, str)
                else left == right
            )
            return equal if self.op == "=" else not equal
        sign = _order_key(left, right, dialect)
        return {
            "<": sign < 0,
            "<=": sign <= 0,
            ">": sign > 0,
            ">=": sign >= 0,
        }[self.op]


@dataclass(frozen=True, slots=True)
class Not:
    inner: Expression

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        value = self.inner.evaluate(row, dialect)
        truth = truth_of(value)
        if truth is Truth.UNKNOWN:
            return NULL
        return truth.negate() is Truth.TRUE


@dataclass(frozen=True, slots=True)
class IsNull:
    """IS NULL, which is the one predicate that never returns UNKNOWN.

    Included because it is how a query author works around the three-valued
    logic, and because on Oracle it answers TRUE for an empty string, which is
    the divergence that turns a data-quality check into a no-op.
    """

    inner: Expression

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        return is_null(self.inner.evaluate(row, dialect))


@dataclass(frozen=True, slots=True)
class NullIf:
    """NULLIF, the standard guard against dividing by zero.

    Present because the suite needs to show what guarding does and does not buy.
    It removes the divide-by-zero axis from a query and leaves the integer
    division axis exactly where it was, which surprises people who have been
    told that NULLIF makes a ratio safe.

    Its own comparison goes through the dialect, so on a case-insensitive
    warehouse NULLIF(region, 'EMEA') nulls out 'emea' too.
    """

    value: Expression
    sentinel: Expression

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        left = self.value.evaluate(row, dialect)
        right = self.sentinel.evaluate(row, dialect)
        if is_null(left) or is_null(right):
            return left
        equal = Binary("=", Literal(left), Literal(right)).evaluate(row, dialect)
        return NULL if equal is True else left


@dataclass(frozen=True, slots=True)
class Concat:
    parts: tuple[Expression, ...]

    def evaluate(self, row: Row, dialect: Dialect) -> Value:
        rendered: list[str] = []
        for part in self.parts:
            value = part.evaluate(row, dialect)
            if is_null(value):
                if dialect.concat_with_null_is_null:
                    return NULL
                continue
            rendered.append(value if isinstance(value, str) else str(value))
        return "".join(rendered)


def evaluate(expression: Expression, row: Row, dialect: Dialect) -> Value:
    return expression.evaluate(row, dialect)
