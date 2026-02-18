"""Pytest configuration and shared fixtures."""

import tempfile
from pathlib import Path

import pytest

from did_webplus.store import SQLiteDIDDocStore


@pytest.fixture
def temp_db() -> Path:
    """Return path to a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    path.unlink(missing_ok=True)


@pytest.fixture
def store(temp_db: Path) -> SQLiteDIDDocStore:
    """Return a SQLiteDIDDocStore backed by a temp database."""
    return SQLiteDIDDocStore(temp_db)
