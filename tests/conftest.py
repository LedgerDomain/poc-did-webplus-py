"""Pytest configuration and shared fixtures."""

import json
import tempfile
from pathlib import Path

import pytest

from did_webplus.store import SQLiteDIDDocStore

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
LEDGERDOMAIN_DIR = FIXTURES_DIR / "microledgers" / "ledgerdomain"


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


@pytest.fixture
def ledgerdomain_fixtures() -> list[dict]:
    """Load ledgerdomain manifest and return entries with fixture paths."""
    manifest_path = LEDGERDOMAIN_DIR / "manifest.json"
    if not manifest_path.exists():
        return []
    manifest = json.loads(manifest_path.read_text())
    entries = manifest.get("entries", [])
    result = []
    for entry in entries:
        root_hash = entry["root_self_hash"]
        jsonl_path = LEDGERDOMAIN_DIR / f"{root_hash}.jsonl"
        if jsonl_path.exists():
            result.append({**entry, "jsonl_path": jsonl_path})
    return result


@pytest.fixture
def ledgerdomain_did_1(ledgerdomain_fixtures: list[dict]) -> dict | None:
    """First ledgerdomain DID and fixture path."""
    return ledgerdomain_fixtures[0] if ledgerdomain_fixtures else None


@pytest.fixture
def ledgerdomain_did_2(ledgerdomain_fixtures: list[dict]) -> dict | None:
    """Second ledgerdomain DID and fixture path."""
    return ledgerdomain_fixtures[1] if len(ledgerdomain_fixtures) > 1 else None
