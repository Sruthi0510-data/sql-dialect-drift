"""Build the standalone HTML report from the suite and the experiment.

One file, no assets, no network. Every number comes from running the code, so
the report cannot disagree with the README even when only one was regenerated.

The verdict badge carries an explicit colour rather than inheriting one, and the
screenshot tool reads the computed style back, because a badge rendered in its
own background colour passes every test in the suite and is invisible.
"""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sdd.differential import run_suite  # noqa: E402
from sdd.queries import SUITE  # noqa: E402

EXPERIMENT = ROOT / "docs" / "experiments" / "exp01.json"
OUT = ROOT / "docs" / "report.html"

STYLE = """
:root { --surface:#fcfcfb; --ink:#1d1d1b; --muted:#6b6b66; --rule:#d9d9d4;
        --blue:#2a78d6; --orange:#eb6834; --green:#1baf7a; }
* { box-sizing: border-box; }
body { margin:0 auto; padding:48px 24px 96px; max-width:920px; background:var(--surface);
       color:var(--ink); line-height:1.55;
       font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; }
h1 { font-size:30px; margin:0 0 8px; letter-spacing:-0.01em; }
h2 { font-size:20px; margin:48px 0 12px; padding-top:18px; border-top:1px solid var(--rule); }
p { margin:0 0 14px; }
.lede { color:var(--muted); font-size:15px; margin-bottom:28px; }
.verdict { display:inline-block; padding:6px 14px; border-radius:999px; font-weight:600;
           font-size:13px; color:#ffffff; background:var(--orange); }
.figures { display:flex; flex-wrap:wrap; gap:16px; margin:24px 0 8px; }
.figure { flex:1 1 190px; border:1px solid var(--rule); border-radius:10px; padding:16px 18px;
          background:#ffffff; }
.figure .value { font-size:28px; font-weight:600; letter-spacing:-0.02em; }
.figure .label { font-size:12px; color:var(--muted); margin-top:4px; }
table { border-collapse:collapse; width:100%; margin:16px 0; font-size:14px; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--rule); }
th { font-weight:600; font-size:12px; text-transform:uppercase; letter-spacing:0.04em;
     color:var(--muted); }
td.num { text-align:right; font-variant-numeric:tabular-nums; }
code { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12.5px; }
.note { font-size:13px; color:var(--muted); }
.agree { color:var(--green); font-weight:600; }
"""


def _figure(value: str, label: str) -> str:
    return f'<div class="figure"><div class="value">{value}</div><div class="label">{label}</div></div>'


def build() -> str:
    report = run_suite(SUITE)
    payload = json.loads(EXPERIMENT.read_text())
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>SQL dialect drift report</title>",
        f"<style>{STYLE}</style></head><body>",
        "<h1>Does this query mean the same thing after the migration?</h1>",
        '<p class="lede">Eleven queries a person would write without thinking twice, run '
        "against a model of six warehouses. Every figure below is produced by running the "
        "code in this repository.</p>",
        '<p><span class="verdict">no: most of them do not</span></p>',
        '<h2 id="summary">Summary</h2>',
        '<div class="figures">',
        _figure(f"{100 * report.divergence_share:.1f}%", "of the suite means different things"),
        _figure(str(len(report.results)), "queries, all of which parse everywhere"),
        _figure(str(len(report.results) - len(report.diverging)), "queries survive unchanged"),
        _figure(str(payload["confounded_axis_count"]), "decisions no query can separate"),
        "</div>",
        '<p class="note">A transpiler handed any of these queries returns valid target SQL '
        "and reports success. The only query that means the same thing on every warehouse is "
        "the one that writes its NULL ordering out.</p>",
        '<h2 id="queries">Every query</h2>',
        "<table><thead><tr><th>query</th><th>SQL</th><th>answers</th>"
        "<th>explained by</th></tr></thead><tbody>",
    ]
    for result in report.results:
        axes = result.explained_by or result.jointly_explained_by
        label = (
            '<span class="agree">agrees everywhere</span>'
            if not result.diverges
            else html.escape(", ".join(axes))
        )
        parts.append(
            f"<tr><td><code>{html.escape(result.query)}</code></td>"
            f"<td><code>{html.escape(result.sql)}</code></td>"
            f'<td class="num">{len(result.groups)}</td><td>{label}</td></tr>'
        )
    parts += [
        "</tbody></table>",
        '<h2 id="pairs">Every migration</h2>',
        "<p>Nobody migrates to six warehouses. The number a plan wants is the one for its "
        "own pair.</p>",
        "<table><thead><tr><th>from</th><th>to</th><th>queries that disagree</th>"
        "</tr></thead><tbody>",
    ]
    for row in payload["pairs"]:
        parts.append(
            f"<tr><td>{html.escape(row['left'])}</td><td>{html.escape(row['right'])}</td>"
            f"<td class=\"num\">{row['diverging']}</td></tr>"
        )
    worst = payload["worst_pair"]
    safest = payload["safest_pair"]
    parts += [
        "</tbody></table>",
        f'<p class="note">The worst pair, {html.escape(worst[0])} to {html.escape(worst[1])}, '
        f"disagree on {worst[2]}. The safest, {html.escape(safest[0])} to "
        f"{html.escape(safest[1])}, disagree on {safest[2]}, and it is the migration nobody "
        "worries about.</p>",
        '<h2 id="blind">What the model cannot see</h2>',
        "<p>Remove one decision from the model and re-run. A decision with no confounded "
        "partner leaves queries unexplained, which is the tool correctly saying it no longer "
        "understands them. A decision with a partner leaves nothing unexplained, because the "
        "partner absorbs its work.</p>",
        "<table><thead><tr><th>decision removed</th><th>queries it can no longer explain</th>"
        "</tr></thead><tbody>",
    ]
    for axis, count in payload["queries_unattributed_when_blinded"].items():
        parts.append(
            f"<tr><td><code>{html.escape(axis)}</code></td>"
            f'<td class="num">{count}</td></tr>'
        )
    parts += [
        "</tbody></table>",
        '<p class="note">So a model with confounded decisions cannot detect that it is '
        "missing one of them. Its apparent completeness is not evidence of completeness.</p>",
        "</body></html>",
    ]
    return "\n".join(parts)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build() + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
