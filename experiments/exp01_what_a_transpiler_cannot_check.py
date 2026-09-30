"""Everything a transpiler would report as a success, and what it would be wrong about.

One experiment, because the repository makes one claim and the claim is a
counting argument: every query in the suite parses on every warehouse, and most
of them mean different things. The experiment counts both, splits the
divergences by which decision produced them, and prices the one fix the suite
contains.

It also runs the suite for every pair of warehouses, because nobody migrates to
six at once and the number a migration plan wants is the one for its own pair.
"""

from __future__ import annotations

import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdd.dialects import DIALECTS, DIVERGENCE_AXES, dialect  # noqa: E402
from sdd.differential import run_suite  # noqa: E402
from sdd.queries import SUITE  # noqa: E402


def main() -> dict[str, object]:
    report = run_suite(SUITE)
    pairs = []
    for left, right in combinations(sorted(DIALECTS), 2):
        narrow = run_suite(SUITE, [dialect(left), dialect(right)])
        pairs.append(
            {
                "left": left,
                "right": right,
                "diverging": len(narrow.diverging),
                "queries": len(narrow.results),
            }
        )
    pairs.sort(key=lambda row: (-row["diverging"], row["left"], row["right"]))

    blinded = {}
    for axis in DIVERGENCE_AXES:
        reduced = run_suite(SUITE, None, [a for a in DIVERGENCE_AXES if a != axis])
        blinded[axis] = len(reduced.unexplained)

    fix = next(result for result in report.results if result.query == "top-balances-explicit-nulls")
    unfixed = next(result for result in report.results if result.query == "top-balances")

    return {
        "warehouses": len(report.dialects),
        "queries": len(report.results),
        "parse_everywhere": len(report.results),
        "diverging": len(report.diverging),
        "divergence_share": report.divergence_share,
        "agreeing": len(report.results) - len(report.diverging),
        "needing_two_decisions": len(report.needing_two_axes),
        "unattributed": len(report.unexplained),
        "confounded_groups": [list(group) for group in report.confounded_axes()],
        "confounded_axis_count": sum(len(group) for group in report.confounded_axes()),
        "axis_counts": report.axis_counts(),
        "worst_pair": list(report.worst_pair()),
        "safest_pair": [pairs[-1]["left"], pairs[-1]["right"], pairs[-1]["diverging"]],
        "pairs": pairs,
        "pairs_with_no_divergence": sum(1 for row in pairs if row["diverging"] == 0),
        "pair_count": len(pairs),
        "fix_groups": len(fix.groups),
        "unfixed_groups": len(unfixed.groups),
        "queries_unattributed_when_blinded": blinded,
        "worst_blind_spot": max(blinded.items(), key=lambda item: item[1])[0],
        "worst_blind_spot_count": max(blinded.values()),
    }


if __name__ == "__main__":
    payload = main()
    (ROOT / "docs" / "experiments").mkdir(parents=True, exist_ok=True)
    (ROOT / "docs" / "experiments" / "exp01.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in payload.items() if k != "pairs"}, indent=2))
