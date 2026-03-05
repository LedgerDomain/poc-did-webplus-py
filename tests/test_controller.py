"""Tests for the did:webplus DID controller."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx

from did_webplus.controller import (
    ControllerError,
    create_did,
    deactivate_did,
    load_key,
    save_key,
    update_did,
)
from did_webplus.did import parse_vdr_url, resolution_path


def test_parse_vdr_url_localhost() -> None:
    c = parse_vdr_url("http://localhost:8085")
    assert c.host == "localhost"
    assert c.port == 8085
    assert c.path is None
    assert c.host_part_for_did() == "localhost%3A8085"


def test_parse_vdr_url_with_path() -> None:
    c = parse_vdr_url("https://example.com:3000/abc")
    assert c.host == "example.com"
    assert c.port == 3000
    assert c.path == "abc"
    assert c.host_part_for_did() == "example.com%3A3000"


def test_resolution_path() -> None:
    did = "did:webplus:example.com:uFiXXX123/did-documents.jsonl"
    # Use a real-looking DID
    did = "did:webplus:localhost:uFiC9wGOLc7j0fWE3D-0rH5hQooYOWpDdmBBcCI_aKEvlnw"
    path = resolution_path(did)
    assert path.endswith("did-documents.jsonl")
    assert "uFiC9wGOLc7j0fWE3D-0rH5hQooYOWpDdmBBcCI_aKEvlnw" in path


def test_key_path_uses_did_as_subdir(tmp_path: Path) -> None:
    """Key is stored in subdir named by the DID itself."""
    from jwcrypto import jwk

    did = "did:webplus:example.com:uFiXXX"
    kid = f"{did}?selfHash=uFiXXX&versionId=0#0"
    key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    save_key(tmp_path, did, key, kid=kid)
    assert (tmp_path / did / "privkey.json").exists()
    loaded = load_key(tmp_path, did)
    assert loaded["kid"] == kid
    assert loaded["x"] == key["x"]


def test_save_and_load_key(tmp_path: Path) -> None:
    from jwcrypto import jwk

    key = jwk.JWK.generate(kty="OKP", crv="Ed25519")
    did = "did:webplus:example.com:uFiXXX"
    kid = f"{did}?selfHash=uFiXXX&versionId=0#0"
    save_key(tmp_path, did, key, kid=kid)
    loaded = load_key(tmp_path, did)
    assert loaded["kid"] == kid
    assert loaded["x"] == key["x"]


def test_load_key_not_found(tmp_path: Path) -> None:
    with pytest.raises(ControllerError, match="No key found"):
        load_key(tmp_path, "did:webplus:example.com:uFiXXX")


@respx.mock
def test_create_did_success(tmp_path: Path) -> None:
    respx.post(url__regex=r"http://localhost:8085/.*/did-documents\.jsonl$").mock(
        return_value=respx.MockResponse(200)
    )
    did = create_did("http://localhost:8085", tmp_path)
    assert did.startswith("did:webplus:localhost")
    assert did.split(":")[-1].startswith("u")  # multibase base64url prefix
    loaded = load_key(tmp_path, did)
    assert loaded is not None


@respx.mock
def test_create_did_vdr_failure(tmp_path: Path) -> None:
    respx.post(url__regex=r".*").mock(return_value=respx.MockResponse(400, text="Bad"))
    with pytest.raises(ControllerError, match="VDR POST failed"):
        create_did("http://localhost:8085", tmp_path)
