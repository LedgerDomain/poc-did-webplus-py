"""
Comprehensive tests for did:webplus using real DID fixtures.

Uses tests/fixtures/microledgers/ledgerdomain/ — real DIDs with real microledgers
from ledgerdomain.github.io. Exercises resolution, DID-to-URL mapping, chain
structure, update rules, and expected output regression.

Run `uv run python scripts/fetch_ledgerdomain_fixtures.py` to populate fixtures.
Run with `--capture-expected` to generate tests/fixtures/expected/ for regression.

Note: Full validation (self-hash, JWS proofs) is not run on these fixtures because
they were produced by the Rust implementation; JCS serialization differences cause
self-hash mismatch. Chain structure (prevDIDDocumentSelfHash, versionId, validFrom)
and resolution behavior are fully tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from did_webplus.did import did_to_resolution_url, parse_did, parse_did_with_query
from did_webplus.document import DIDDocument, parse_did_document
from did_webplus.resolver import FullDIDResolver, _validate_document
from did_webplus.store import SQLiteDIDDocStore

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
LEDGERDOMAIN_DIR = FIXTURES_DIR / "microledgers" / "ledgerdomain"
EXPECTED_DIR = FIXTURES_DIR / "expected"


def _load_ledgerdomain_fixtures() -> list[dict]:
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


def _load_microledger(jsonl_path: Path) -> list[dict]:
    """Load microledger as list of parsed documents."""
    lines = [ln.strip() for ln in jsonl_path.read_text().strip().split("\n") if ln.strip()]
    return [json.loads(ln) for ln in lines]


# --- Fixtures ---


@pytest.fixture
def ledgerdomain_fixtures() -> list[dict]:
    """All ledgerdomain fixture entries."""
    return _load_ledgerdomain_fixtures()


@pytest.fixture
def ledgerdomain_did_1(ledgerdomain_fixtures: list[dict]) -> dict | None:
    """First ledgerdomain DID (uFiDBw4x... — has deactivated tombstone at v2)."""
    return ledgerdomain_fixtures[0] if ledgerdomain_fixtures else None


@pytest.fixture
def ledgerdomain_did_2(ledgerdomain_fixtures: list[dict]) -> dict | None:
    """Second ledgerdomain DID (uFiANVlM... — has hashedKey at v2)."""
    return ledgerdomain_fixtures[1] if len(ledgerdomain_fixtures) > 1 else None


def _requires_fixtures(fixtures: list[dict] | None) -> None:
    if not fixtures:
        pytest.skip("Ledgerdomain fixtures not found; run fetch_ledgerdomain_fixtures.py")


# --- DID-to-URL mapping (spec §DID resolution URL) ---


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_did_to_resolution_url_matches_manifest(entry: dict) -> None:
    """DID string maps to resolution URL per spec; matches manifest."""
    did = entry["did"]
    expected_url = entry["resolution_url"]
    actual_url = did_to_resolution_url(did)
    assert actual_url == expected_url, f"DID resolution URL mismatch for {did}"


def test_parse_ledgerdomain_dids(ledgerdomain_fixtures: list[dict]) -> None:
    """All fixture DIDs parse correctly."""
    _requires_fixtures(ledgerdomain_fixtures)
    for entry in ledgerdomain_fixtures:
        parsed = parse_did(entry["did"])
        assert parsed.root_self_hash == entry["root_self_hash"]
        assert "ledgerdomain.github.io" in parsed.host
        assert parsed.path == "did-webplus-spec"


def test_parse_did_with_query_params(ledgerdomain_fixtures: list[dict]) -> None:
    """DID URLs with ?versionId and ?selfHash parse correctly."""
    _requires_fixtures(ledgerdomain_fixtures)
    entry = ledgerdomain_fixtures[0]
    did = entry["did"]
    root_hash = entry["root_self_hash"]

    p = parse_did_with_query(f"{did}?versionId=0")
    assert p.did == did
    assert p.query_version_id == 0
    assert p.query_self_hash is None

    p = parse_did_with_query(f"{did}?selfHash={root_hash}")
    assert p.did == did
    assert p.query_self_hash == root_hash
    assert p.query_version_id is None


# --- Chain structure (prevDIDDocumentSelfHash, versionId, validFrom) ---


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_chain_structure(entry: dict) -> None:
    """Each microledger has valid chain: prev hash, versionId+1, validFrom monotonic."""
    docs = _load_microledger(entry["jsonl_path"])
    assert len(docs) >= 1, "Microledger must have at least one document"

    prev_doc: DIDDocument | None = None
    for i, doc_dict in enumerate(docs):
        doc = parse_did_document(json.dumps(doc_dict))
        doc.verify_chain_constraints(prev_doc)
        if prev_doc is not None:
            assert doc.prevDIDDocumentSelfHash == prev_doc.selfHash
            assert doc.versionId == prev_doc.versionId + 1
        prev_doc = doc


# --- Document structure (root vs non-root, update rules, deactivation) ---


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_root_document_structure(entry: dict) -> None:
    """Root document (v0) has no prevDIDDocumentSelfHash, versionId=0, has updateRules."""
    docs = _load_microledger(entry["jsonl_path"])
    root = docs[0]
    assert "prevDIDDocumentSelfHash" not in root or root["prevDIDDocumentSelfHash"] is None
    assert root["versionId"] == 0
    assert root["selfHash"] == entry["root_self_hash"]
    assert "updateRules" in root and root["updateRules"]
    assert "key" in root["updateRules"] or "hashedKey" in root["updateRules"] or "any" in root["updateRules"]


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_non_root_has_proofs(entry: dict) -> None:
    """Non-root documents have proofs array with at least one JWS."""
    docs = _load_microledger(entry["jsonl_path"])
    for doc in docs[1:]:
        assert "proofs" in doc and isinstance(doc["proofs"], list)
        assert len(doc["proofs"]) >= 1, f"Non-root doc v{doc['versionId']} must have proofs"


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_document_id_consistency(entry: dict) -> None:
    """All documents in a microledger share the same DID (id field)."""
    docs = _load_microledger(entry["jsonl_path"])
    did = entry["did"]
    for doc in docs:
        assert doc["id"] == did


def test_deactivated_tombstone_present(ledgerdomain_did_1: dict | None) -> None:
    """uFiDBw4x... ends with deactivated document (updateRules: {})."""
    _requires_fixtures([ledgerdomain_did_1] if ledgerdomain_did_1 else [])
    docs = _load_microledger(ledgerdomain_did_1["jsonl_path"])
    last = docs[-1]
    assert last["updateRules"] == {}
    assert last["versionId"] == 2


# --- Resolution ---


@pytest.mark.asyncio
async def test_resolve_both_dids(
    store: SQLiteDIDDocStore,
    ledgerdomain_fixtures: list[dict],
) -> None:
    """Resolve latest for both fixture DIDs."""
    _requires_fixtures(ledgerdomain_fixtures)
    resolver = FullDIDResolver(store)

    for entry in ledgerdomain_fixtures:
        lines = [ln.strip() for ln in entry["jsonl_path"].read_text().strip().split("\n") if ln.strip()]
        await store.add_did_documents(lines, 0)

        result = await resolver.resolve(entry["did"], no_fetch=True)
        assert result.did_document
        doc = json.loads(result.did_document)
        assert doc["id"] == entry["did"]
        assert result.did_document_metadata.version_id == entry["document_count"] - 1


@pytest.mark.asyncio
async def test_resolve_by_version_id_all(
    store: SQLiteDIDDocStore,
    ledgerdomain_fixtures: list[dict],
) -> None:
    """Resolve each versionId (0, 1, 2) for each fixture DID."""
    _requires_fixtures(ledgerdomain_fixtures)
    resolver = FullDIDResolver(store)

    for entry in ledgerdomain_fixtures:
        lines = [ln.strip() for ln in entry["jsonl_path"].read_text().strip().split("\n") if ln.strip()]
        await store.add_did_documents(lines, 0)

        docs = _load_microledger(entry["jsonl_path"])
        for i, expected_doc in enumerate(docs):
            result = await resolver.resolve(f"{entry['did']}?versionId={i}")
            assert result.did_document_metadata.version_id == i
            resolved_doc = json.loads(result.did_document)
            assert resolved_doc["selfHash"] == expected_doc["selfHash"]


@pytest.mark.asyncio
async def test_resolve_by_self_hash(
    store: SQLiteDIDDocStore,
    ledgerdomain_fixtures: list[dict],
) -> None:
    """Resolve by ?selfHash=... matches ?versionId=0 for root."""
    _requires_fixtures(ledgerdomain_fixtures)
    resolver = FullDIDResolver(store)

    for entry in ledgerdomain_fixtures:
        lines = [ln.strip() for ln in entry["jsonl_path"].read_text().strip().split("\n") if ln.strip()]
        await store.add_did_documents(lines, 0)

        root_hash = entry["root_self_hash"]
        result_v0 = await resolver.resolve(f"{entry['did']}?versionId=0")
        result_sh = await resolver.resolve(f"{entry['did']}?selfHash={root_hash}")
        assert result_sh.did_document == result_v0.did_document


# --- Full verification + resolution (self-hash, chain, proofs) ---


LEDGERDOMAIN_DIDS = [
    "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiDBw4xANa8sR_Fd8-pv-X9A5XIJNS3tC_bRNB3HUYiKug",
    "did:webplus:ledgerdomain.github.io:did-webplus-spec:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow",
]


@pytest.mark.parametrize("did", LEDGERDOMAIN_DIDS)
@pytest.mark.asyncio
async def test_resolve_ledgerdomain_did_with_full_verification(
    store: SQLiteDIDDocStore,
    did: str,
) -> None:
    """
    Resolve ledgerdomain DIDs with full verification (self-hash, chain, proofs).

    DID resolution includes validation of each document in the chain before
    returning the resolved document. This test ensures both DIDs pass.
    """
    fixtures = _load_ledgerdomain_fixtures()
    entry = next((e for e in fixtures if e["did"] == did), None)
    if not entry:
        pytest.skip("Ledgerdomain fixtures not found; run fetch_ledgerdomain_fixtures.py")

    lines = [ln.strip() for ln in entry["jsonl_path"].read_text().strip().split("\n") if ln.strip()]
    prev_doc = None
    for line in lines:
        doc_dict = json.loads(line)
        _validate_document(line, doc_dict, prev_doc)
        prev_doc = doc_dict

    await store.add_did_documents(lines, 0)
    resolver = FullDIDResolver(store)
    result = await resolver.resolve(did, no_fetch=True)

    assert result.did_document
    doc = json.loads(result.did_document)
    assert doc["id"] == did
    assert result.did_document_metadata.version_id == entry["document_count"] - 1


# --- Expected resolution output regression ---


def _get_expected_paths() -> list[tuple[dict, Path]]:
    """Return (entry, expected_path) for entries that have expected output."""
    fixtures = _load_ledgerdomain_fixtures()
    result = []
    for entry in fixtures:
        root_hash = entry["root_self_hash"]
        expected_path = EXPECTED_DIR / f"{root_hash}_resolution.json"
        if expected_path.exists():
            result.append((entry, expected_path))
    return result


@pytest.mark.asyncio
async def test_resolution_matches_expected(
    store: SQLiteDIDDocStore,
) -> None:
    """Resolved output matches expected/ regression files when present."""
    pairs = _get_expected_paths()
    if not pairs:
        pytest.skip("No expected resolution files; run fetch_ledgerdomain_fixtures.py --capture-expected")

    for entry, expected_path in pairs:
        expected = json.loads(expected_path.read_text())
        lines = [ln.strip() for ln in entry["jsonl_path"].read_text().strip().split("\n") if ln.strip()]
        await store.add_did_documents(lines, 0)

        resolver = FullDIDResolver(store)
        result = await resolver.resolve(entry["did"], no_fetch=True)

        assert result.did_document == expected["didDocument"], f"Mismatch for {entry['root_self_hash'][:20]}"
        assert result.did_document_metadata.version_id == expected["didDocumentMetadata"]["versionId"]
        assert result.did_document_metadata.deactivated == expected["didDocumentMetadata"].get("deactivated", False)
        assert result.did_resolution_metadata.did_document_resolved_locally == expected["didResolutionMetadata"]["didDocumentResolvedLocally"]


# --- Update rules variants ---


def test_update_rules_key_on_root(ledgerdomain_fixtures: list[dict]) -> None:
    """Root documents use key or hashedKey update rules."""
    _requires_fixtures(ledgerdomain_fixtures)
    for entry in ledgerdomain_fixtures:
        docs = _load_microledger(entry["jsonl_path"])
        root_rules = docs[0]["updateRules"]
        assert "key" in root_rules, "Root should have key rule"
        assert root_rules["key"].startswith("u"), "Key should be base64url multicodec"


def test_update_rules_hashed_key_on_updates(ledgerdomain_fixtures: list[dict]) -> None:
    """Non-root documents use hashedKey in update rules (except deactivated)."""
    _requires_fixtures(ledgerdomain_fixtures)
    for entry in ledgerdomain_fixtures:
        docs = _load_microledger(entry["jsonl_path"])
        for doc in docs[1:]:
            if doc["updateRules"]:  # not deactivated
                assert "hashedKey" in doc["updateRules"]
                assert doc["updateRules"]["hashedKey"].startswith("u")


# --- VerificationMethod and DID URL references ---


@pytest.mark.parametrize("entry", _load_ledgerdomain_fixtures(), ids=lambda e: e["root_self_hash"][:20])
def test_verification_method_ids_include_self_hash(entry: dict) -> None:
    """VerificationMethod id URLs include selfHash and versionId params."""
    docs = _load_microledger(entry["jsonl_path"])
    for doc in docs:
        for vm in doc.get("verificationMethod", []):
            vm_id = vm.get("id", "")
            if "?" in vm_id:
                assert "selfHash=" in vm_id
                assert "versionId=" in vm_id
