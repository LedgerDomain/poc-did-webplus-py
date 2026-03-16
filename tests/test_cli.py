"""Tests for the did-webplus CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
import rfc8785

from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.store import SQLiteDIDDocStore


def _make_root_doc() -> str:
    doc = {
        "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        "updateRules": {},
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    compute_self_hash(doc)
    return rfc8785.dumps(doc).decode("utf-8")


def test_cli_resolve_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI resolve prints result when DID is in store."""
    store_path = tmp_path / "did_documents.db"
    store = SQLiteDIDDocStore(store_path)
    jcs = _make_root_doc()
    import asyncio
    asyncio.run(store.add_did_documents([jcs], 0))

    did = json.loads(jcs)["id"]
    monkeypatch.chdir(tmp_path)

    from typer.testing import CliRunner
    runner = CliRunner()
    from did_webplus.cli import app
    result = runner.invoke(
        app,
        ["resolve", did, "--base-dir", str(tmp_path), "--no-fetch", "-o", "json"],
    )
    assert result.exit_code == 0
    out = json.loads(result.output)
    assert out["didDocument"]
    assert out["didResolutionMetadata"]["didDocumentResolvedLocally"] is True


def test_cli_resolve_error_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CLI outputs W3C-style error result when -o json and resolution fails."""
    monkeypatch.chdir(tmp_path)

    from typer.testing import CliRunner
    runner = CliRunner()
    from did_webplus.cli import app
    result = runner.invoke(
        app,
        ["resolve", "did:webplus:example.com:nonexistent", "--base-dir", str(tmp_path), "--no-fetch", "-o", "json"],
    )
    assert result.exit_code == 1
    out = json.loads(result.output)
    assert out["didDocument"] is None
    assert out["didResolutionMetadata"]["error"]
    assert "not found" in out["didResolutionMetadata"]["error"].lower()


@respx.mock
def test_cli_did_create_success(tmp_path: Path) -> None:
    """CLI did create prints DID on success."""
    respx.post(url__regex=r".*did-documents\.jsonl$").mock(
        return_value=respx.MockResponse(200)
    )
    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    result = runner.invoke(
        app,
        ["did", "create", "http://localhost:8085", "--base-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    fully_qualified_did = result.output.strip()
    assert fully_qualified_did.startswith("did:webplus:localhost")
    # The controller stores keys under the base DID (without query params)
    did = fully_qualified_did.split("?")[0]
    # Key is stored in subdir named by the DID itself
    assert (tmp_path / did / "privkey.json").exists()


@respx.mock
def test_cli_did_create_vdr_failure(tmp_path: Path) -> None:
    """CLI did create exits 1 when VDR returns error."""
    respx.post(url__regex=r".*").mock(return_value=respx.MockResponse(400, text="Bad"))
    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    result = runner.invoke(
        app,
        ["did", "create", "http://localhost:8085", "--base-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "VDR POST failed" in result.output
