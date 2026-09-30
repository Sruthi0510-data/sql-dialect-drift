# ADR-002: the attribution refuses to guess, in three different ways

## Status

Accepted. This is the decision the repository is for.

## Context

Reporting that two warehouses disagree is easy and nearly useless. The question
is which decision produced the disagreement, because that is what a migration
plan acts on and what a fix targets.

The tempting implementation walks the modelled decisions, returns the first that
could explain the split, and moves on. It produces a clean table, it is one line
shorter, and it is wrong in three separate ways that are invisible in its
output.

## Decision

Attribution matches partitions and reports every match.

A decision explains a split when partitioning the warehouses by that decision's
value produces exactly the partition the answers produced. The function returns
every decision that matches, not the first.

When no single decision matches, pairs are searched, and every matching pair is
reported, flattened. A query whose predicate touches two behaviours at once
produces a partition finer than either decision alone, and calling that
unexplained would blame the model for something the query did.

When neither search matches, the result is `unexplained` and the CLI exits 4. It
is a different exit code from a finding because it should reach a different
person.

Pairs are searched and triples are not. A query needing three decisions is a
query doing too much, and the right response is to split the query rather than
widen the search.

## Consequences

The measured answer is more honest and less tidy. 4 of the six modelled
decisions fall into two confounded pairs, and every finding involving them names
both members, which looks like indecision and is not: separating them requires a
warehouse that differs on one and not the other, and this repository does not
model one.

The confounding then produces the result worth the whole exercise. Removing a
confounded decision from the model leaves nothing unexplained, because its
partner absorbs every query it used to explain. A model with confounded
decisions cannot detect that it is missing one of them, so its apparent
completeness is not evidence of completeness. `--blind` exists so that a reader
can reproduce that in one command.

## Alternatives considered

**Returning the first matching decision.** Rejected: it converts "these two are
indistinguishable" into "it is this one", which is a coin flip reported as a
finding.

**Scoring decisions by how many queries they explain and picking the highest.**
Rejected for the same reason with more arithmetic. A confounded pair scores
identically by construction, so the tie-break would be alphabetical order
wearing a statistic.

**Treating a two-decision split as unexplained.** Rejected because it blames the
model for the query's complexity, and because the three-way split it produces is
the most realistic query in the suite.
