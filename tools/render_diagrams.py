"""Emit the README's diagram as SVG, with every number read from the metrics.

Hand-written SVG rather than Mermaid, for the usual four reasons: Mermaid does
not render in a PDF export, does not render in an editor preview that is not
GitHub, chooses its own layout so a longer label makes it illegible, and cannot
read a number from a metrics file, which leaves every figure in it unguarded.

Colours are the three from the shared palette on the light surface, and every
text element carries an explicit fill so a reader on a dark theme gets the same
picture rather than black text on a dark background.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METRICS = ROOT / "docs" / "metrics.json"
OUT = ROOT / "docs" / "img"

SURFACE = "#fcfcfb"
INK = "#1d1d1b"
MUTED = "#6b6b66"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREEN = "#1baf7a"
RULE = "#d9d9d4"
FONT = "font-family=\"-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif\""


def _text(x, y, content, *, size=13, fill=INK, weight="400", anchor="start", mono=False):
    family = 'font-family="ui-monospace, SFMono-Regular, Menlo, monospace"' if mono else FONT
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" {family} font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{content}</text>'
    )


def how_a_query_splits(metrics: dict) -> str:
    """One query, six warehouses, two answers, and the clause that removes the gap."""
    width, height = 880, 380
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" role="img" aria-labelledby="title desc">',
        "<title id=\"title\">How one query splits six warehouses</title>",
        "<desc id=\"desc\">The same ORDER BY returns two different top-three lists across six "
        "warehouses because NULLs sort last on three of them and first on the other three. "
        "Adding NULLS LAST collapses the two answers into one.</desc>",
        f'<rect width="{width}" height="{height}" fill="{SURFACE}"/>',
        _text(24, 34, "One ranking, two answers", size=17, weight="600"),
        _text(
            24,
            58,
            "SELECT account FROM ledger ORDER BY balance_cents, account LIMIT 3",
            size=12.5,
            fill=MUTED,
            mono=True,
        ),
    ]

    # Read from the suite rather than typed in. A hand-typed answer in a diagram
    # is a figure nothing re-measures, which is the one thing this repository's
    # tooling exists to prevent, and it would be the only such figure here.
    import sys

    sys.path.insert(0, str(ROOT / "src"))
    from sdd.dialects import DIALECTS, NullOrder
    from sdd.differential import run_query
    from sdd.queries import query

    result = run_query(query("top-balances"), tuple(DIALECTS.values()))
    by_answer: dict[str, list[str]] = {}
    for answer in result.answers:
        by_answer.setdefault(answer.rendered(), []).append(answer.dialect)
    ordered = sorted(
        by_answer.items(),
        key=lambda item: DIALECTS[item[1][0]].null_order_asc is NullOrder.FIRST,
    )
    panels = [
        (
            tuple(sorted(names)),
            rendered.replace("'", ""),
            colour,
            f"NULLs sort {DIALECTS[names[0]].null_order_asc.value}",
        )
        for (rendered, names), colour in zip(ordered, (BLUE, ORANGE))
    ]

    for index, (names, answer, colour, label) in enumerate(panels):
        top = 92 + index * 118
        parts.append(
            f'<rect x="24" y="{top}" width="832" height="98" rx="8" fill="none" '
            f'stroke="{RULE}" stroke-width="1.5"/>'
        )
        parts.append(_text(44, top + 28, label, size=13, weight="600", fill=colour))
        parts.append(_text(44, top + 52, "  ".join(names), size=12.5, fill=MUTED))
        parts.append(_text(44, top + 78, answer, size=13.5, mono=True))

    parts.append(
        f'<rect x="24" y="330" width="832" height="36" rx="8" fill="none" '
        f'stroke="{GREEN}" stroke-width="1.5"/>'
    )
    parts.append(
        _text(
            44,
            353,
            "ORDER BY balance_cents NULLS LAST  ->  all six agree",
            size=13,
            fill=GREEN,
            weight="600",
            mono=True,
        )
    )
    parts.append(
        _text(
            856,
            353,
            f"{metrics['unfixed_groups']} answers becomes {metrics['fix_groups']}",
            size=12,
            fill=MUTED,
            anchor="end",
        )
    )
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> int:
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))["metrics"]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "how-a-query-splits.svg").write_text(how_a_query_splits(metrics) + "\n", encoding="utf-8")
    print(f"wrote 1 diagram to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
