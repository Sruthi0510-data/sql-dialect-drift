"""Measures the gap between a transpiler's output parsing and its meaning the same thing.

A transpiler takes a query written for one warehouse and returns a query the
target warehouse accepts. Acceptance is what it can check and acceptance is not
what anybody wanted. The question asked of a migration is whether the numbers
come out the same, and no amount of syntactic validity answers it.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
