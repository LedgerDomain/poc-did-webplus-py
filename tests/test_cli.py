"""Tests for the did-webplus CLI."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import respx
import rfc8785

from did_webplus.resolution import ResolutionOptions
from did_webplus.resolver import ResolutionResult
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
        [
            "resolve",
            "did:webplus:example.com:nonexistent",
            "--base-dir",
            str(tmp_path),
            "--local-resolution-only",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 1
    out = json.loads(result.output)
    assert out["didDocument"] is None
    assert out["didDocumentMetadata"] == {}
    error = out["didResolutionMetadata"]["error"]
    assert isinstance(error, dict)
    assert error["type"]
    assert error["detail"]
    assert out["didResolutionMetadata"]["fetchedUpdatesFromVDR"] is False
    assert out["didResolutionMetadata"]["didDocumentResolvedLocally"] is False
    # No metadata groups requested → metadata locality is vacuously true.
    assert out["didResolutionMetadata"]["didDocumentMetadataResolvedLocally"] is True


def test_cli_resolve_flags_map_to_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI resolution flags build one ResolutionOptions passed to the resolver."""
    captured: dict[str, object] = {}

    def fake_resolve_or_result_sync(
        self: object,
        did_query: str,
        *,
        no_fetch: bool = False,
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        captured["did_query"] = did_query
        captured["no_fetch"] = no_fetch
        captured["options"] = options
        return ResolutionResult(
            did_document='{"id":"did:webplus:example.com:abc"}',
            did_document_metadata={"versionId": "0"},
            did_resolution_metadata={
                "contentType": "application/did+json",
                "fetchedUpdatesFromVDR": False,
                "didDocumentResolvedLocally": True,
                "didDocumentMetadataResolvedLocally": True,
            },
        )

    monkeypatch.setattr(
        "did_webplus.cli.FullDIDResolver.resolve_or_result_sync",
        fake_resolve_or_result_sync,
    )

    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    result = runner.invoke(
        app,
        [
            "resolve",
            "did:webplus:example.com:abc",
            "--base-dir",
            str(tmp_path),
            "--creation",
            "--next",
            "--latest",
            "--deactivated",
            "--local-resolution-only",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    opts = captured["options"]
    assert isinstance(opts, ResolutionOptions)
    assert opts == ResolutionOptions(
        request_create=True,
        request_next=True,
        request_latest=True,
        request_deactivated=True,
        local_resolution_only=True,
    )
    assert captured["no_fetch"] is False


def test_cli_resolve_no_fetch_aliases_local_resolution_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--no-fetch is a compatibility alias for localResolutionOnly."""
    captured: dict[str, object] = {}

    def fake_resolve_or_result_sync(
        self: object,
        did_query: str,
        *,
        no_fetch: bool = False,
        options: ResolutionOptions | None = None,
    ) -> ResolutionResult:
        captured["options"] = options
        return ResolutionResult(
            did_document=None,
            did_document_metadata={},
            did_resolution_metadata={
                "contentType": "application/did+json",
                "error": {
                    "type": "https://www.w3.org/ns/did#NOT_FOUND",
                    "title": "Not Found",
                    "detail": "missing",
                },
                "fetchedUpdatesFromVDR": False,
                "didDocumentResolvedLocally": False,
                "didDocumentMetadataResolvedLocally": True,
            },
        )

    monkeypatch.setattr(
        "did_webplus.cli.FullDIDResolver.resolve_or_result_sync",
        fake_resolve_or_result_sync,
    )

    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    result = runner.invoke(
        app,
        [
            "resolve",
            "did:webplus:example.com:abc",
            "--base-dir",
            str(tmp_path),
            "--no-fetch",
            "-o",
            "json",
        ],
    )
    assert result.exit_code == 1
    opts = captured["options"]
    assert isinstance(opts, ResolutionOptions)
    assert opts.local_resolution_only is True
    out = json.loads(result.output)
    assert out["didDocument"] is None
    assert isinstance(out["didResolutionMetadata"]["error"], dict)


def test_cli_resolve_creation_metadata_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--creation gates created metadata in JSON success output."""
    store_path = tmp_path / "did_documents.db"
    store = SQLiteDIDDocStore(store_path)
    jcs = _make_root_doc()
    asyncio.run(store.add_did_documents([jcs], 0))
    did = json.loads(jcs)["id"]
    monkeypatch.chdir(tmp_path)

    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    without = runner.invoke(
        app,
        [
            "resolve",
            f"{did}?versionId=0",
            "--base-dir",
            str(tmp_path),
            "--local-resolution-only",
            "-o",
            "json",
        ],
    )
    assert without.exit_code == 0, without.output
    out_without = json.loads(without.output)
    assert "created" not in out_without["didDocumentMetadata"]

    with_creation = runner.invoke(
        app,
        [
            "resolve",
            f"{did}?versionId=0",
            "--base-dir",
            str(tmp_path),
            "--creation",
            "--local-resolution-only",
            "-o",
            "json",
        ],
    )
    assert with_creation.exit_code == 0, with_creation.output
    out_with = json.loads(with_creation.output)
    assert out_with["didDocumentMetadata"]["created"] == "2024-01-01T00:00:00Z"
    # Zero fractional ms normalizes without a fractional component.
    assert (
        out_with["didDocumentMetadata"]["createdMilliseconds"]
        == "2024-01-01T00:00:00Z"
    )


def test_cli_resolve_error_pretty_renders_structured_detail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pretty output prints error title/detail; JSON shape unchanged on failure."""
    monkeypatch.chdir(tmp_path)

    from typer.testing import CliRunner

    runner = CliRunner()
    from did_webplus.cli import app

    pretty = runner.invoke(
        app,
        [
            "resolve",
            "did:webplus:example.com:nonexistent",
            "--base-dir",
            str(tmp_path),
            "--local-resolution-only",
            "-o",
            "pretty",
        ],
    )
    assert pretty.exit_code == 1
    assert ":" in pretty.output or pretty.stderr
    # stderr or combined output should mention a structured title/detail
    combined = (pretty.output or "") + (pretty.stderr or "")
    assert combined.strip()

    as_json = runner.invoke(
        app,
        [
            "resolve",
            "did:webplus:example.com:nonexistent",
            "--base-dir",
            str(tmp_path),
            "--local-resolution-only",
            "-o",
            "json",
        ],
    )
    assert as_json.exit_code == 1
    out = json.loads(as_json.output)
    assert out["didDocument"] is None
    assert isinstance(out["didResolutionMetadata"]["error"], dict)


def test_interop_python_cmd_maps_all_options() -> None:
    """Interop adapter maps every wire option to a Python CLI flag."""
    resolvers_path = (
        Path(__file__).resolve().parents[1] / "interop" / "resolvers.py"
    )
    spec = importlib.util.spec_from_file_location(
        "interop_resolvers_under_test", resolvers_path
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Dataclass processing requires the module to be registered.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

    assert all(mod.PYTHON_OPTION_SUPPORT.values())
    opts = mod.ResolutionOptions(
        request_create=True,
        request_next=True,
        request_latest=True,
        request_deactivated=True,
        local_resolution_only=True,
    )
    assert mod._unsupported_for(opts, mod.PYTHON_OPTION_SUPPORT) == ()
    cmd = mod._build_python_cmd(
        "did:webplus:example.com:abc", Path("/tmp/store"), opts, None
    )
    assert "--creation" in cmd
    assert "--next" in cmd
    assert "--latest" in cmd
    assert "--deactivated" in cmd
    assert "--local-resolution-only" in cmd
    assert "--no-fetch" not in cmd


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
