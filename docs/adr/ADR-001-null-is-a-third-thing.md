# ADR-001: NULL is a third thing, and there is no parser

## Status

Accepted.

## Context

Two decisions were made together because they trade against each other.

The first is how to represent SQL values. The obvious choice is Python values
with `None` for NULL, and it produces a model that is wrong in exactly the
places the interesting divergences live. `None` is falsy, so a predicate that
returns NULL is indistinguishable from one that returns FALSE, and the
difference between them is why `WHERE x <> 'a'` silently drops the rows where x
is NULL. `None` also compares and sorts, so a model built on it answers
questions SQL has no answer for.

The second is whether to parse SQL. A real parser would let the suite hold query
text rather than expression trees, which reads better and is what a transpiler
actually consumes.

## Decision

Tagged values with a `NULL` singleton and an explicit three-valued `Truth`, and
no parser.

`NULL` is not `None`. It raises on `bool()`, so the wrong idiom fails loudly
rather than producing a plausible answer. `Truth` has TRUE, FALSE and UNKNOWN as
distinct members, with `keeps_row()` and `passes_constraint()` as separate
methods because a WHERE clause and a CHECK constraint treat UNKNOWN oppositely,
and a model that collapsed them could not express that.

Queries are expression trees. Each carries the SQL text it stands for as a
string, for the reader, and that string is never parsed.

## Consequences

The value model pays for itself immediately: every divergence involving NULL is
expressible, and several of them are the ones that matter most.

Not parsing costs something real. The SQL text beside each query is
documentation, and documentation can drift from the tree it describes. Nothing
in the build checks that `SELECT balance_cents / 2` is what `Binary("/",
Column("balance_cents"), Literal(2))` means, and a reader has to take it on
trust. That is the single weakest point in the repository and it is recorded
here rather than buried.

The mitigation is that the trees are small enough to read in full, and that the
one place the mismatch nearly happened was caught: a query whose SQL said
`NULLIF(settled_cents, 0)` was built with a tree that did not guard the zero,
which made its declared reason for existing false. It now has a `NullIf` node,
and the guard is real.

## Alternatives considered

**A real parser.** Rejected on the code-to-argument ratio. A hand-written SQL
parser is several hundred lines that a reader must audit before believing any
result, and the results here need six operators.

**Depending on an existing parser.** Rejected because the repository would then
be measuring that library's model of SQL rather than its own, and the whole
claim is about what a tool's model cannot see.
