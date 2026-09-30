"""Re-measure every published figure and write docs/metrics.json.

Nothing is typed by hand. The test count and the coverage come from pytest's
machine readable reports, and every other figure comes from the experiment,
which is produced by running the experiment.

Anchors pair each value with two or three words of its context, because a
checker that searches for digits passes happily while the sentence around them
has gone stale.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from render_tables import table_values  # noqa: E402

DOCS = ROOT / "docs"
EXPERIMENT = ROOT / "experiments" / "exp01_what_a_transpiler_cannot_check.py"
EXPERIMENT_OUTPUT = DOCS / "experiments" / "exp01.json"
JUNIT = ROOT / "junit.xml"
COVERAGE_JSON = ROOT / "coverage.json"
METRICS_PATH = DOCS / "metrics.json"

CHECKED_DOCUMENTS = [
    "README.md",
    "docs/adr/ADR-001-null-is-a-third-thing.md",
    "docs/adr/ADR-002-attribution-refuses-to-guess.md",
    "docs/adr/ADR-003-what-this-repository-cannot-measure.md",
]

ANCHORS: dict[str, list[str]] = {
    "tests_total": ["{} tests,"],
    "coverage_line_pct": ["{}% line"],
    "coverage_branch_pct": ["{}% branch"],
    "warehouses": ["{} warehouses"],
    "queries": ["{} queries a person"],
    "diverging": ["{} of them mean"],
    "divergence_pct": ["{}% of the suite"],
    "agreeing": ["{} query survives"],
    "needing_two_decisions": ["{} query needs two"],
    "confounded_axis_count": ["{} of the six decisions"],
    "worst_pair_count": ["worst pair disagree on {}"],
    "safest_pair_count": ["pairs disagree on {} of"],
    "pairs_with_no_divergence": ["{} of the fifteen pairs"],
    "worst_blind_spot_count": ["only {} of them become"],
    "fix_groups": ["goes to {} answer"],
    "unfixed_groups": ["from {} answers"],
    "unattributed": ["leaves {} unattributable"],
}


def run_tests() -> None:
    subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "--cov=sdd", f"--cov-report=json:{COVERAGE_JSON}", f"--junitxml={JUNIT}",
        ],
        cwd=ROOT,
        check=True,
    )


def read_test_count() -> int:
    root = ET.parse(JUNIT).getroot()
    suite = root if root.tag == "testsuite" else root[0]
    return int(suite.get("tests", 0))


def read_coverage() -> tuple[float, float]:
    totals = json.loads(COVERAGE_JSON.read_text())["totals"]
    line = round(float(totals["percent_covered"]), 1)
    covered, total = totals.get("covered_branches", 0), totals.get("num_branches", 0)
    return line, (round(100.0 * covered / total, 1) if total else 100.0)


def build_metrics(skip_tests: bool) -> dict[str, Any]:
    if not skip_tests:
        run_tests()
    line_pct, branch_pct = read_coverage()
    subprocess.run([sys.executable, str(EXPERIMENT)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    payload = json.loads(EXPERIMENT_OUTPUT.read_text())

    metrics = {
        "tests_total": read_test_count(),
        "coverage_line_pct": line_pct,
        "coverage_branch_pct": branch_pct,
        "warehouses": payload["warehouses"],
        "queries": payload["queries"],
        "diverging": payload["diverging"],
        "divergence_pct": round(100 * payload["divergence_share"], 1),
        "agreeing": payload["agreeing"],
        "needing_two_decisions": payload["needing_two_decisions"],
        "unattributed": payload["unattributed"],
        "confounded_axis_count": payload["confounded_axis_count"],
        "worst_pair_count": payload["worst_pair"][2],
        "safest_pair_count": payload["safest_pair"][2],
        "pairs_with_no_divergence": payload["pairs_with_no_divergence"],
        "fix_groups": payload["fix_groups"],
        "unfixed_groups": payload["unfixed_groups"],
        "worst_blind_spot_count": payload["worst_blind_spot_count"],
    }
    return {
        "metrics": metrics,
        "table_values": table_values(),
        "anchors": ANCHORS,
        "checked_documents": CHECKED_DOCUMENTS,
        "note": (
            "every value here is produced by running the suite and the experiment; "
            "tools/check_numbers.py fails the build when a document quotes a figure the code "
            "no longer produces"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="re-measure every published figure")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    payload = build_metrics(skip_tests=args.skip_tests)
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {METRICS_PATH.relative_to(ROOT)} with {len(payload['metrics'])} metrics")
    for name, value in sorted(payload["metrics"].items()):
        print(f"  {name:<28} {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
