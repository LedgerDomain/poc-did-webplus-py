"""Tests for DID parsing and URL mapping."""

import pytest

from did_webplus.did import (
    DIDComponents,
    MalformedDIDError,
    parse_did,
    parse_did_with_query,
    did_to_resolution_url,
)


def test_parse_simple_did() -> None:
    did = "did:webplus:example.com:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    c = parse_did(did)
    assert c.host == "example.com"
    assert c.port is None
    assert c.path is None
    assert c.root_self_hash == "uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"


def test_parse_did_with_path() -> None:
    did = "did:webplus:example.com:path-component:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    c = parse_did(did)
    assert c.host == "example.com"
    assert c.port is None
    assert c.path == "path-component"
    assert c.root_self_hash == "uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"


def test_parse_did_with_port() -> None:
    did = "did:webplus:example.com%3A3000:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    c = parse_did(did)
    assert c.host == "example.com"
    assert c.port == 3000
    assert c.path is None


def test_parse_did_with_port_and_path() -> None:
    did = "did:webplus:example.com%3A3000:a:very:long:path:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    c = parse_did(did)
    assert c.host == "example.com"
    assert c.port == 3000
    assert c.path == "a:very:long:path"


def test_parse_localhost() -> None:
    did = "did:webplus:localhost:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    c = parse_did(did)
    assert c.host == "localhost"
    assert c.hostname() == "localhost"


def test_reject_non_webplus() -> None:
    with pytest.raises(MalformedDIDError):
        parse_did("did:web:example.com:123")


def test_reject_fragment() -> None:
    with pytest.raises(MalformedDIDError):
        parse_did_with_query("did:webplus:example.com:abc#frag")


def test_parse_did_with_query_params() -> None:
    parsed = parse_did_with_query(
        "did:webplus:example.com:abc?selfHash=xyz&versionId=1"
    )
    assert parsed.did == "did:webplus:example.com:abc"
    assert parsed.query_self_hash == "xyz"
    assert parsed.query_version_id == 1


def test_parse_did_without_query() -> None:
    parsed = parse_did_with_query("did:webplus:example.com:abc")
    assert parsed.query_self_hash is None
    assert parsed.query_version_id is None


def test_resolution_url_example_com() -> None:
    did = "did:webplus:example.com:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    url = did_to_resolution_url(did)
    assert url == "https://example.com/uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA/did-documents.jsonl"


def test_resolution_url_with_path() -> None:
    did = "did:webplus:example.com:path-component:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    url = did_to_resolution_url(did)
    assert url == "https://example.com/path-component/uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA/did-documents.jsonl"


def test_resolution_url_with_port() -> None:
    did = "did:webplus:example.com%3A3000:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    url = did_to_resolution_url(did)
    assert url == "https://example.com:3000/uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA/did-documents.jsonl"


def test_resolution_url_localhost_uses_http() -> None:
    did = "did:webplus:localhost:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    url = did_to_resolution_url(did)
    assert url.startswith("http://")
    assert "localhost" in url
