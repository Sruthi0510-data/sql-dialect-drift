# ADR-003: what this repository cannot measure

## Status

Accepted. This file exists so nobody has to guess whether an omission was an
oversight.

## Six decisions, not a catalogue

The model carries six behavioural decisions. SQL has more, and the ones missing
are missing for stated reasons rather than by accident.

**Time zones and timestamp types.** The largest family by cost and the one left
out. `TIMESTAMP` means with-time-zone on some warehouses and without on others,
`CURRENT_DATE` is evaluated in UTC on some and in a session zone on others, and
a date truncation can move a row into a different day. Modelling it honestly
needs a time-zone database, a session-settings model and a notion of when a
query ran, which is more machinery than the rest of the repository combined and
would make the argument harder rather than clearer.

**Numeric precision and scale.** Decimal arithmetic differs in where rounding
happens and how scale propagates through division. It is modelled here only as
the integer-versus-exact division axis, which is the coarsest possible version.

**Implicit casting.** `'10' > 9` is an error on some warehouses and a comparison
on others, and the comparison itself can be lexical or numeric. The evaluator
raises on mixed-type comparison instead, which is one warehouse's behaviour
presented as everybody's.

**Collation beyond case.** Accent sensitivity, locale-dependent ordering and
Unicode normalisation are all real and none is modelled. `string_compare_case_sensitive`
is a boolean standing in for a family.

**Aggregate and window semantics.** `COUNT(DISTINCT)`, approximate aggregates,
window frame defaults and the treatment of NULL inside aggregates all diverge.
The suite has no aggregate at all.

## The warehouses are a model, not a test environment

Every field in `dialects.py` is a claim about somebody's product, carried with a
note saying what the vendor documents. No test can check those claims, because
checking them requires the warehouse. A reader whose cluster behaves differently
is usually right, and the usual reason is a session setting: `ERROR_FOR_DIVISION_BY_ZERO`,
a non-default collation, a `NULLS FIRST` default set at the account level.

The right way to use this repository is as an argument about what a transpiler
cannot check, not as a reference for what your warehouse does.

## Confounded decisions cannot be separated from inside

4 of the six decisions fall into two pairs that partition these six warehouses
identically. No query can tell them apart, and the repository reports both names
rather than choosing. Separating them requires adding a warehouse that differs
on one and not the other, which is a change to the model, not a change to the
suite.

## The SQL text is not checked against the tree

Each query carries the SQL it stands for as a string, and nothing verifies that
the string and the expression tree mean the same thing. ADR-001 records this as
the weakest point in the repository. It is mitigated by the trees being small
and by one near-miss having been caught, and it is not eliminated.

## Eleven queries is a demonstration, not a survey

The divergence share is 90.9% on a suite chosen to contain divergences. It is
not an estimate of how many queries in a real codebase diverge, it is a
demonstration that ordinary queries do, and the README says so where the number
appears.
