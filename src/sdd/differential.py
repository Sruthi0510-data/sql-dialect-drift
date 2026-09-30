"""Run every query on every warehouse and say why the answers split the way they do.

Grouping dialects by answer is easy. Saying which of the six modelled decisions
produced the grouping is the part that turns a diff into something a migration
plan can act on, and it is done by matching partitions rather than by guessing.

For a query whose answers split the six dialects into groups, an axis explains
the split when partitioning the dialects by that axis's value produces the same
partition. If exactly one axis matches, the divergence is attributed to it. If
several match, the axes are confounded on this suite and the finding says so
rather than picking the first. If none matches, the split has a cause the model
does not carry, which is a finding about the model and is reported as one.

The last case is not hypothetical and it is the reason the attribution is
written this way. Two axes that happen to divide these six warehouses
identically cannot be told apart by any query, and a tool that reported one of
them would be inventing a certainty the data does not contain.

Every function here takes the axis set as an argument rather than reading the
module constant. That exists for `--blind`, which drops a decision from the
model and re-runs, and which is the only honest way this repository has of
talking about its own incompleteness: a reader who wants to know what the tool
looks like when it does not know about a behaviour can make it not know about
one and watch it say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from sdd.dialects import DIALECTS, DIVERGENCE_AXES, Dialect
from sdd.expressions import DivisionByZero
from sdd.queries import Query
from sdd.table import rows_as_dicts
from sdd.values import NULL, Value

__all__ = [
    "Answer",
    "QueryResult",
    "Report",
    "run_query",
    "run_suite",
    "explain_split",
    "explain_jointly",
]


@dataclass(frozen=True, slots=True)
class Answer:
    """What one warehouse returned, including the case where it refused.

    An error is an answer. "This query raises on five warehouses and returns a
    number on the sixth" is the most expensive divergence in the catalogue,
    because the migration looks fine in testing against the warehouse that
    raises and silently produces rows on the one that does not.
    """

    dialect: str
    values: tuple[Value, ...] | None
    error: str | None = None

    @property
    def failed(self) -> bool:
        return self.error is not None

    def rendered(self) -> str:
        if self.error is not None:
            return f"error: {self.error}"
        return ", ".join("NULL" if value is NULL else repr(value) for value in self.values or ())


@dataclass(frozen=True, slots=True)
class QueryResult:
    """One query across every warehouse, with the split and its explanation."""

    query: str
    sql: str
    declared_axis: str
    answers: tuple[Answer, ...]
    groups: tuple[tuple[str, ...], ...]
    explained_by: tuple[str, ...]
    jointly_explained_by: tuple[str, ...]
    why: str

    @property
    def diverges(self) -> bool:
        return len(self.groups) > 1

    @property
    def unexplained(self) -> bool:
        return self.diverges and not self.explained_by and not self.jointly_explained_by

    @property
    def needs_two_axes(self) -> bool:
        """Whether no single decision accounts for the split but a pair does.

        A real category. A predicate can touch case folding and the empty string
        at once, and the warehouses then fall into three groups that neither
        axis produces alone. Reporting it as unexplained would blame the model
        for something the query did.
        """
        return self.diverges and not self.explained_by and bool(self.jointly_explained_by)

    @property
    def confounded(self) -> bool:
        return len(self.explained_by) > 1

    @property
    def raises_somewhere(self) -> bool:
        return any(answer.failed for answer in self.answers)

    @property
    def raises_everywhere(self) -> bool:
        return all(answer.failed for answer in self.answers)

    @property
    def declaration_holds(self) -> bool:
        """Whether the query's own claim about why it diverges survived measurement.

        A query that says it exercises integer division and turns out to split
        the warehouses along the divide-by-zero axis was written by somebody who
        was wrong about their own example, and a test fails the build over it.
        """
        if not self.diverges:
            return self.declared_axis == "none"
        return self.declared_axis in (self.explained_by or self.jointly_explained_by)


@dataclass(frozen=True, slots=True)
class Report:
    results: tuple[QueryResult, ...]
    dialects: tuple[str, ...]
    axes: tuple[str, ...] = DIVERGENCE_AXES

    @property
    def diverging(self) -> tuple[QueryResult, ...]:
        return tuple(result for result in self.results if result.diverges)

    @property
    def divergence_share(self) -> float:
        if not self.results:
            return 0.0
        return len(self.diverging) / len(self.results)

    @property
    def unexplained(self) -> tuple[QueryResult, ...]:
        return tuple(result for result in self.results if result.unexplained)

    @property
    def confounded(self) -> tuple[QueryResult, ...]:
        return tuple(result for result in self.results if result.confounded)

    @property
    def needing_two_axes(self) -> tuple[QueryResult, ...]:
        return tuple(result for result in self.results if result.needs_two_axes)

    def axis_counts(self) -> dict[str, int]:
        counts = {axis: 0 for axis in self.axes}
        for result in self.diverging:
            for axis in result.explained_by or result.jointly_explained_by:
                counts[axis] += 1
        return counts

    def confounded_axes(self) -> tuple[tuple[str, ...], ...]:
        """Groups of decisions that no query on these warehouses can tell apart.

        Two axes are indistinguishable when they partition the chosen warehouses
        identically, which happens whenever the same single warehouse is the odd
        one out on both. It is a property of the six chosen, not of SQL, and it
        is reported because an attribution that names one member of such a group
        is reporting a coin flip as a finding.
        """
        partitions: dict[frozenset[frozenset[str]], list[str]] = {}
        for axis in self.axes:
            key = _partition(
                self.dialects, lambda name, axis=axis: getattr(DIALECTS[name], axis)
            )
            partitions.setdefault(key, []).append(axis)
        return tuple(
            tuple(group) for group in partitions.values() if len(group) > 1
        )

    def worst_pair(self) -> tuple[str, str, int]:
        """The two warehouses that disagree on the most queries.

        The number a migration actually wants, because nobody migrates to all
        six. Returns the pair and the count, with ties broken alphabetically so
        the answer is stable.
        """
        worst = ("", "", -1)
        for index, left in enumerate(self.dialects):
            for right in self.dialects[index + 1 :]:
                count = sum(
                    1
                    for result in self.results
                    if _group_of(result, left) != _group_of(result, right)
                )
                if count > worst[2]:
                    worst = (left, right, count)
        return worst


def _group_of(result: QueryResult, name: str) -> int:
    for index, group in enumerate(result.groups):
        if name in group:
            return index
    raise KeyError(f"{name} is not in the result for {result.query}")  # pragma: no cover


def _partition(names: Sequence[str], key) -> frozenset[frozenset[str]]:
    buckets: dict[object, set[str]] = {}
    for name in names:
        buckets.setdefault(key(name), set()).add(name)
    return frozenset(frozenset(bucket) for bucket in buckets.values())


def explain_split(
    groups: Sequence[Sequence[str]],
    dialects: Sequence[str],
    axes: Sequence[str] = DIVERGENCE_AXES,
) -> tuple[str, ...]:
    """Which modelled decisions partition the warehouses exactly as the answers do.

    Returns every matching axis, not the first. An empty result means the split
    has a cause outside the model; more than one means the suite cannot tell
    those axes apart, which is a statement about the six warehouses chosen and
    not about the world.
    """
    observed = frozenset(frozenset(group) for group in groups)
    matches: list[str] = []
    for axis in axes:
        if _partition(dialects, lambda name, axis=axis: getattr(DIALECTS[name], axis)) == observed:
            matches.append(axis)
    return tuple(matches)


def explain_jointly(
    groups: Sequence[Sequence[str]],
    dialects: Sequence[str],
    axes: Sequence[str] = DIVERGENCE_AXES,
) -> tuple[str, ...]:
    """The smallest pair of decisions whose combination produces the observed split.

    Two axes taken together partition the warehouses by the pair of values, and
    a query that touches both lands in that finer partition. Searching pairs
    rather than all subsets is deliberate: a suite that needed three axes to
    explain one query would be a suite whose queries do too much, and ADR-002
    records that as a reason to split the query rather than to widen the search.

    Every matching pair is returned, flattened and deduplicated, rather than the
    first. Axes that are confounded across the chosen warehouses produce several
    matching pairs, and naming one of them would be inventing a certainty the
    six warehouses do not contain.
    """
    observed = frozenset(frozenset(group) for group in groups)
    matched: list[str] = []
    for left, right in combinations(axes, 2):
        partition = _partition(
            dialects,
            lambda name, left=left, right=right: (
                getattr(DIALECTS[name], left),
                getattr(DIALECTS[name], right),
            ),
        )
        if partition == observed:
            for axis in (left, right):
                if axis not in matched:
                    matched.append(axis)
    return tuple(matched)


def run_query(
    query: Query,
    dialects: Sequence[Dialect],
    axes: Sequence[str] = DIVERGENCE_AXES,
) -> QueryResult:
    rows = rows_as_dicts()
    answers: list[Answer] = []
    for dialect in dialects:
        try:
            answers.append(Answer(dialect=dialect.name, values=query.answer(rows, dialect)))
        except DivisionByZero as exc:
            answers.append(Answer(dialect=dialect.name, values=None, error=str(exc)))
    buckets: dict[str, list[str]] = {}
    for answer in answers:
        buckets.setdefault(answer.rendered(), []).append(answer.dialect)
    groups = tuple(tuple(sorted(names)) for names in buckets.values())
    names = tuple(dialect.name for dialect in dialects)
    explained = explain_split(groups, names, axes) if len(groups) > 1 else ()
    joint = explain_jointly(groups, names, axes) if len(groups) > 1 and not explained else ()
    return QueryResult(
        query=query.name,
        sql=query.sql,
        declared_axis=query.axis,
        answers=tuple(answers),
        groups=groups,
        explained_by=explained,
        jointly_explained_by=joint,
        why=query.why,
    )


def run_suite(
    suite: Sequence[Query],
    dialects: Sequence[Dialect] | None = None,
    axes: Sequence[str] = DIVERGENCE_AXES,
) -> Report:
    chosen = tuple(dialects) if dialects is not None else tuple(DIALECTS.values())
    return Report(
        results=tuple(run_query(query, chosen, axes) for query in suite),
        dialects=tuple(dialect.name for dialect in chosen),
        axes=tuple(axes),
    )
