"""Shared fixtures. Thin on purpose: most tests build the two values they need inline."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sdd.dialects import DIALECTS  # noqa: E402
from sdd.table import rows_as_dicts  # noqa: E402


@pytest.fixture(scope="session")
def rows():
    return rows_as_dicts()


@pytest.fixture(scope="session")
def every_dialect():
    return tuple(DIALECTS.values())
