"""Tests for DID parsing and URL mapping."""

import pytest

from did_webplus.did import (
    DIDComponents,
    MalformedDIDError,
    parse_did,
    parse_did_with_query,
    parse_http_scheme_overrides,
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


def test_parse_http_scheme_overrides() -> None:
    assert parse_http_scheme_overrides(None) == {}
    assert parse_http_scheme_overrides("") == {}
    assert parse_http_scheme_overrides("rust-vdr=http,python-vdr=http") == {
        "rust-vdr": "http",
        "python-vdr": "http",
    }
    assert parse_http_scheme_overrides("example.com=https") == {"example.com": "https"}
    # Invalid schemes are skipped
    assert parse_http_scheme_overrides("a=ftp,b=http") == {"b": "http"}
    # Hostnames normalized to lowercase
    assert parse_http_scheme_overrides("Rust-VDR=HTTP") == {"rust-vdr": "http"}


def test_resolution_url_http_scheme_override() -> None:
    did = "did:webplus:rust-vdr%3A8085:uHiBKHZUE3HHlYcyVIF-vPm0Xg71vqJla2L1OGXHMSK4NEA"
    # Default: rust-vdr is not localhost, so https
    url = did_to_resolution_url(did)
    assert url.startswith("https://")
    # Override: rust-vdr=http
    overrides = {"rust-vdr": "http"}
    url = did_to_resolution_url(did, http_scheme_overrides=overrides)
    assert url.startswith("http://")
    assert "rust-vdr:8085" in url
