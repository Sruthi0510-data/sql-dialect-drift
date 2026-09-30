"""Capture this repository's own commands and commit the transcript.

The command list is the README's claims, in the order the README makes them. If
a claim changes, the list changes with it, and the capture fails the build when
a command does not exit the way the README says it does, so all four documented
exit codes are demonstrated rather than asserted.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from capture_terminal import Step, capture  # noqa: E402

PY = sys.executable

STEPS = [
    Step(
        label="the suite, with branch coverage",
        argv=[PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--cov=sdd",
              "--cov-branch", "--cov-report=term-missing", "--cov-fail-under=100"],
        max_lines=16,
        tail_lines=4,
    ),
    Step(
        label="every query on every warehouse: a finding",
        argv=[PY, "-m", "sdd.cli", "check"],
        expect=3,
        max_lines=22,
    ),
    Step(
        label="the migration nobody worries about, which is the one that is safe",
        argv=[PY, "-m", "sdd.cli", "check", "--dialect", "postgres", "--dialect", "redshift"],
        expect=0,
        max_lines=9,
        tail_lines=0,
    ),
    Step(
        label="one query, every answer, and the decision behind the split",
        argv=[PY, "-m", "sdd.cli", "explain", "top-balances"],
        expect=3,
        max_lines=17,
    ),
    Step(
        label="the same query with its NULL ordering written out",
        argv=[PY, "-m", "sdd.cli", "explain", "top-balances-explicit-nulls"],
        expect=0,
        max_lines=13,
        tail_lines=2,
    ),
    Step(
        label="decisions these six warehouses cannot separate",
        argv=[PY, "-m", "sdd.cli", "confounded"],
        expect=0,
        max_lines=8,
    ),
    Step(
        label="the tool with one decision removed from its model: a refusal",
        argv=[PY, "-m", "sdd.cli", "check", "--blind", "null_order_asc"],
        expect=4,
        max_lines=10,
        tail_lines=0,
    ),
    Step(
        label="a warehouse this repository does not model",
        argv=[PY, "-m", "sdd.cli", "check", "--dialect", "duckdb"],
        expect=2,
        max_lines=3,
    ),
    Step(
        label="every published figure re-checked against the prose",
        argv=[PY, "tools/check_numbers.py"],
        max_lines=3,
    ),
]


def main() -> int:
    return capture(
        STEPS,
        title="sql-dialect-drift: captured by tools/proof_of_work.py, exit codes as returned",
        out_svg=ROOT / "docs" / "img" / "proof-of-work.svg",
        out_json=ROOT / "docs" / "proof-of-work.json",
    )


if __name__ == "__main__":
    raise SystemExit(main())
