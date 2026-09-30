"""The command line, whose exit codes carry the argument.

  0  every query in the suite means the same thing on every warehouse asked
  2  the tool was handed something it cannot work with
  3  a divergence was found: at least one query means different things
  4  a divergence was found that the model cannot attribute to any decision

Three is the tool working. Four is the tool admitting its own model is
incomplete, which is a different thing and should reach a different person: a
three goes to whoever owns the migration, a four goes to whoever owns this
repository.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from sdd.dialects import DIALECTS, DIVERGENCE_AXES, UnknownDialectError, dialect
from sdd.differential import Report, run_query, run_suite
from sdd.queries import SUITE, UnknownQueryError, query
from sdd.table import COLUMNS, rows_as_dicts
from sdd.values import NULL

__all__ = ["main", "OK", "BAD_INPUT", "DIVERGED", "UNATTRIBUTED"]

OK = 0
BAD_INPUT = 2
DIVERGED = 3
UNATTRIBUTED = 4


def _chosen(names: Sequence[str] | None):
    return [dialect(name) for name in (names or sorted(DIALECTS))]


def _axes(blind: Sequence[str] | None) -> tuple[str, ...]:
    """The decisions the model is allowed to explain a divergence with.

    `--blind` removes one. It is the only honest way this tool has of showing
    what it looks like when its model is incomplete, which is the state every
    such tool is really in: there is no reason to believe six decisions are all
    of them, and a reader who wants to see the tool admit that can make it
    forget one.
    """
    if not blind:
        return DIVERGENCE_AXES
    unknown = sorted(set(blind) - set(DIVERGENCE_AXES))
    if unknown:
        available = ", ".join(DIVERGENCE_AXES)
        raise UnknownDialectError(
            f"no such decision: {', '.join(unknown)}; available: {available}"
        )
    return tuple(axis for axis in DIVERGENCE_AXES if axis not in set(blind))


def _verdict(report: Report) -> int:
    if report.unexplained:
        return UNATTRIBUTED
    return DIVERGED if report.diverging else OK


def _cmd_check(args: argparse.Namespace) -> int:
    report = run_suite(SUITE, _chosen(args.dialect), _axes(args.blind))
    print(f"warehouses          {len(report.dialects)}")
    print(f"queries             {len(report.results)}")
    print(f"parse everywhere    {len(report.results)}")
    print(
        f"mean the same thing {len(report.results) - len(report.diverging)}"
        f" ({1 - report.divergence_share:.1%})"
    )
    print(f"diverge             {len(report.diverging)} ({report.divergence_share:.1%})")
    print(f"need two decisions  {len(report.needing_two_axes)}")
    print(f"unattributable      {len(report.unexplained)}")
    left, right, count = report.worst_pair()
    print(f"worst pair          {left} and {right} disagree on {count}")
    print()
    print(f"{'query':32} {'groups':>6}  explained by")
    print("-" * 78)
    for result in report.results:
        axes = result.explained_by or result.jointly_explained_by
        label = "agrees everywhere" if not result.diverges else ", ".join(axes)
        print(f"{result.query:32} {len(result.groups):>6}  {label}")
    return _verdict(report)


def _cmd_explain(args: argparse.Namespace) -> int:
    result = run_query(query(args.query), _chosen(args.dialect), _axes(args.blind))
    print(result.sql)
    print()
    print(f"why it is in the suite: {result.why}")
    print()
    for answer in result.answers:
        print(f"  {answer.dialect:12} {answer.rendered()}")
    print()
    if not result.diverges:
        print("every warehouse asked returns the same answer")
        return OK
    print(f"the answers split the warehouses {len(result.groups)} ways:")
    for group in result.groups:
        print(f"  {', '.join(group)}")
    if result.explained_by:
        print(f"explained by: {', '.join(result.explained_by)}")
        if result.confounded:
            print("these decisions cannot be told apart across the warehouses asked")
        return DIVERGED
    if result.jointly_explained_by:
        print(f"no single decision explains it; two act together, among: "
              f"{', '.join(result.jointly_explained_by)}")
        return DIVERGED
    print("no modelled decision explains this split")
    return UNATTRIBUTED


def _cmd_confounded(args: argparse.Namespace) -> int:
    report = run_suite(SUITE, _chosen(args.dialect), _axes(args.blind))
    groups = report.confounded_axes()
    if not groups:
        print("every modelled decision is distinguishable across the warehouses asked")
        return OK
    print("decisions no query on these warehouses can tell apart:")
    for group in groups:
        print(f"  {', '.join(group)}")
    print()
    print("this is a property of the warehouses chosen, not of SQL. adding a")
    print("warehouse that differs on one and not the other separates them.")
    return OK


def _cmd_table(args: argparse.Namespace) -> int:
    rows = rows_as_dicts()
    print("  ".join(f"{name:>14}" for name in COLUMNS))
    for row in rows:
        print("  ".join(f"{'NULL' if row[name] is NULL else row[name]!s:>14}" for name in COLUMNS))
    return OK


def _cmd_json(args: argparse.Namespace) -> int:
    report = run_suite(SUITE, _chosen(args.dialect), _axes(args.blind))
    payload = {
        "dialects": list(report.dialects),
        "queries": len(report.results),
        "diverging": len(report.diverging),
        "divergence_share": report.divergence_share,
        "confounded_axes": [list(group) for group in report.confounded_axes()],
        "results": [
            {
                "query": result.query,
                "sql": result.sql,
                "groups": [list(group) for group in result.groups],
                "explained_by": list(result.explained_by),
                "jointly_explained_by": list(result.jointly_explained_by),
            }
            for result in report.results
        ],
    }
    text = json.dumps(payload, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return _verdict(report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sdd",
        description="Measure where valid target SQL stops meaning the same thing.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("check", _cmd_check, "run every query on every warehouse"),
        ("confounded", _cmd_confounded, "decisions the chosen warehouses cannot separate"),
        ("json", _cmd_json, "the whole report as JSON"),
    ):
        node = sub.add_parser(name, help=help_text)
        node.add_argument("--dialect", action="append", help="restrict to these warehouses")
        node.add_argument(
            "--blind",
            action="append",
            help="pretend the model does not know about this decision",
        )
        if name == "json":
            node.add_argument("--out", type=Path, default=None)
        node.set_defaults(handler=handler)
    explain = sub.add_parser("explain", help="one query, every warehouse, and the reason")
    explain.add_argument("query")
    explain.add_argument("--dialect", action="append")
    explain.add_argument("--blind", action="append")
    explain.set_defaults(handler=_cmd_explain)
    table = sub.add_parser("table", help="print the fixture table")
    table.set_defaults(blind=None)
    table.set_defaults(handler=_cmd_table)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(args)
    except (UnknownDialectError, UnknownQueryError) as exc:
        print(str(exc).strip('"'), file=sys.stderr)
        return BAD_INPUT


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
