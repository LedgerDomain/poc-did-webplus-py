"""Tests for the did:webplus VDR service."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import rfc8785
from fastapi.testclient import TestClient

from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.store import SQLiteDIDDocStore
from did_webplus.vdr import create_vdr_app, VDRConfig


def _make_root_doc(host: str = "testserver", path_part: str | None = None) -> str:
    doc = {
        "id": f"did:webplus:{host}:{path_part + ':' if path_part else ''}{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {"key": "u7QFCWKaWNQ5FsNShO8BlZwjHa5xkGleeETKwu-vjf1SZXg"},
        "proofs": [],
        "verificationMethod": [
            {
                "id": f"did:webplus:{host}:{path_part + ':' if path_part else ''}{BLAKE3_PLACEHOLDER}?selfHash={BLAKE3_PLACEHOLDER}&versionId=0#0",
                "type": "JsonWebKey2020",
                "controller": f"did:webplus:{host}:{path_part + ':' if path_part else ''}{BLAKE3_PLACEHOLDER}",
                "publicKeyJwk": {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": "lZq_V0eF2PaFk07maitC6e-cMcCkYxkX1ugKRzFgodQ",
                },
            }
        ],
        "authentication": ["#0"],
        "assertionMethod": ["#0"],
        "keyAgreement": ["#0"],
        "capabilityInvocation": ["#0"],
        "capabilityDelegation": ["#0"],
    }
    compute_self_hash(doc)
    return rfc8785.dumps(doc).decode("utf-8")


def test_did_matches_vdr_config_allows_any_port_when_config_port_none(
    vdr_store: SQLiteDIDDocStore,
) -> None:
    """
    When VDRConfig.did_port is None, the VDR should accept DIDs whose host
    includes an explicit port (e.g. localhost%3A8085) as long as the hostname
    matches. This mirrors running the VDR with --did-hostname localhost and
    no --did-port and creating a DID via http://localhost:8085.
    """
    config = VDRConfig(
        did_hostname="localhost",
        did_port=None,
        path_prefix=None,
        vdg_base_urls=[],
        store=vdr_store,
    )
    app = create_vdr_app(config)
    client = TestClient(app)

    # Root document whose id uses host "localhost%3A8085"
    jcs = _make_root_doc(host="localhost%3A8085")
    doc = json.loads(jcs)
    root_hash = doc["selfHash"]
    path_part = root_hash + "/did-documents.jsonl"

    # Simulate client talking to http://localhost:8085
    resp = client.post(f"/{path_part}", content=jcs, headers={"host": "localhost:8085"})
    assert resp.status_code == 200


@pytest.fixture
def vdr_store(tmp_path: Path) -> SQLiteDIDDocStore:
    return SQLiteDIDDocStore(tmp_path / "vdr.db")


@pytest.fixture
def vdr_client(vdr_store: SQLiteDIDDocStore) -> TestClient:
    config = VDRConfig(
        did_hostname="testserver",
        did_port=None,
        path_prefix=None,
        vdg_base_urls=[],
        store=vdr_store,
    )
    app = create_vdr_app(config)
    return TestClient(app)


def test_health(vdr_client: TestClient) -> None:
    resp = vdr_client.get("/health")
    assert resp.status_code == 200


def test_get_404_when_empty(vdr_client: TestClient) -> None:
    resp = vdr_client.get("/uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow/did-documents.jsonl")
    assert resp.status_code == 404


def test_post_create_and_get(vdr_client: TestClient) -> None:
    jcs = _make_root_doc()
    doc = json.loads(jcs)
    did = doc["id"]
    root_hash = doc["selfHash"]
    path_part = root_hash + "/did-documents.jsonl"

    resp = vdr_client.post(f"/{path_part}", content=jcs)
    assert resp.status_code == 200

    resp = vdr_client.get(f"/{path_part}")
    assert resp.status_code == 200
    assert resp.text == jcs


def test_get_with_range(vdr_client: TestClient) -> None:
    jcs = _make_root_doc()
    doc = json.loads(jcs)
    path_part = doc["selfHash"] + "/did-documents.jsonl"

    vdr_client.post(f"/{path_part}", content=jcs)
    total = len(jcs.encode("utf-8")) + 1

    resp = vdr_client.get(f"/{path_part}", headers={"Range": f"bytes={total}-"})
    assert resp.status_code == 416
    assert "Content-Range" in resp.headers

    resp = vdr_client.get(f"/{path_part}", headers={"Range": "bytes=0-"})
    assert resp.status_code == 206
    assert resp.text == jcs


def test_post_rejects_wrong_did(vdr_client: TestClient) -> None:
    jcs = _make_root_doc()
    doc = json.loads(jcs)
    doc["id"] = "did:webplus:other.com:uFiANVlMledNFUBJNiZPuvfgzxvJlGGDBIpDFpM4DXW6Bow"
    jcs_bad = rfc8785.dumps(doc).decode("utf-8")
    path_part = doc["selfHash"] + "/did-documents.jsonl"

    resp = vdr_client.post(f"/{path_part}", content=jcs_bad)
    assert resp.status_code in (400, 403)


def test_404_for_non_did_documents_path(vdr_client: TestClient) -> None:
    resp = vdr_client.get("/some/other/path")
    assert resp.status_code == 404
