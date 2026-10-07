"""Tests for JSONL byte offsets, Range fetch status handling, and atomic ingest."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import respx
import rfc8785
from httpx import Response

from did_webplus.did import parse_did
from did_webplus.resolver import FullDIDResolver, ResolutionError
from did_webplus.selfhash import BLAKE3_PLACEHOLDER, compute_self_hash
from did_webplus.store import SQLiteDIDDocStore


def _make_root_jcs() -> tuple[str, str, str]:
    doc = {
        "id": f"did:webplus:example.com:{BLAKE3_PLACEHOLDER}",
        "selfHash": BLAKE3_PLACEHOLDER,
        "validFrom": "2024-01-01T00:00:00.000Z",
        "versionId": 0,
        # Non-empty updateRules so the tip is not a deactivation tombstone;
        # plain-DID resolution must still plan a VDR fetch.
        "updateRules": {
            "key": "u7QFCWKaWNQ5FsNShO8BlZwjHa5xkGleeETKwu-vjf1SZXg"
        },
        "proofs": [],
        "verificationMethod": [],
        "authentication": [],
        "assertionMethod": [],
        "keyAgreement": [],
        "capabilityInvocation": [],
        "capabilityDelegation": [],
    }
    compute_self_hash(doc)
    jcs = rfc8785.dumps(doc).decode("utf-8")
    return doc["id"], doc["selfHash"], jcs


@pytest.mark.asyncio
async def test_store_octet_length_is_after_final_brace(
    store: SQLiteDIDDocStore,
) -> None:
    _, _, jcs = _make_root_jcs()
    await store.add_did_documents([jcs], 0)
    length = await store.get_microledger_octet_length(json.loads(jcs)["id"])
    assert length == len(jcs.encode("utf-8"))
    assert not jcs.endswith("\n")


@respx.mock
@pytest.mark.asyncio
async def test_incremental_https_range_trailing_newline_only_is_up_to_date(
    store: SQLiteDIDDocStore,
) -> None:
    did, root_hash, jcs = _make_root_jcs()
    await store.add_did_documents([jcs], 0)
    known = len(jcs.encode("utf-8"))
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    respx.get(url).mock(
        return_value=Response(
            206,
            text="\n",
            headers={"Content-Range": f"bytes {known}-{known}/{known + 1}"},
        )
    )

    resolver = FullDIDResolver(store)
    # Plain DID with a non-deactivated tip plans a fetch; suffix is only the
    # source file's trailing newline → no new records, store unchanged.
    result = await resolver.resolve(did)
    assert result.did_document == jcs
    assert (await store.get_latest(did)).version_id == 0
    assert respx.calls.last.request.headers["Range"] == f"bytes={known}-"


@respx.mock
@pytest.mark.asyncio
async def test_incremental_416_matching_total_is_up_to_date(
    store: SQLiteDIDDocStore,
) -> None:
    did, root_hash, jcs = _make_root_jcs()
    await store.add_did_documents([jcs], 0)
    known = len(jcs.encode("utf-8"))
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    respx.get(url).mock(
        return_value=Response(
            416,
            headers={"Content-Range": f"bytes */{known}"},
        )
    )

    resolver = FullDIDResolver(store)
    result = await resolver.resolve(did)
    assert result.did_document == jcs
    assert (await store.get_microledger_octet_length(did)) == known


@respx.mock
@pytest.mark.asyncio
async def test_incremental_rejects_unexpected_full_200(
    store: SQLiteDIDDocStore,
) -> None:
    did, root_hash, jcs = _make_root_jcs()
    await store.add_did_documents([jcs], 0)
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    respx.get(url).mock(return_value=Response(200, text=jcs + "\n" + jcs + "\n"))

    resolver = FullDIDResolver(store)
    with pytest.raises(ResolutionError, match="unexpected HTTP 200"):
        await resolver.resolve(did)
    assert (await store.get_latest(did)).version_id == 0


@respx.mock
@pytest.mark.asyncio
async def test_atomic_rollback_on_invalid_incremental_suffix(
    store: SQLiteDIDDocStore,
) -> None:
    did, root_hash, jcs = _make_root_jcs()
    await store.add_did_documents([jcs], 0)
    known = len(jcs.encode("utf-8"))
    url = f"https://example.com/{root_hash}/did-documents.jsonl"
    # Boundary separator present, but the new record is not valid JSON.
    respx.get(url).mock(
        return_value=Response(
            206,
            text="\n{not-json",
            headers={"Content-Range": f"bytes {known}-{known + 9}/{known + 10}"},
        )
    )

    resolver = FullDIDResolver(store)
    with pytest.raises(ResolutionError, match="invalid JSON"):
        await resolver.resolve(did)

    latest = await store.get_latest(did)
    assert latest is not None
    assert latest.version_id == 0
    assert latest.did_documents_jsonl_octet_length == known
    assert await store.get_microledger_jsonl(did) == jcs


@pytest.mark.parametrize("trailing_newline", [False, True])
@respx.mock
@pytest.mark.asyncio
async def test_incremental_ingest_fixture_trailing_newline_variants(
    trailing_newline: bool,
    ledgerdomain_did_1: dict | None,
) -> None:
    """Warm prefix + 206 suffix works for bodies with/without a final newline."""
    if ledgerdomain_did_1 is None:
        pytest.skip(
            "Ledgerdomain fixtures not found; run fetch_ledgerdomain_fixtures.py"
        )

    lines = [
        ln
        for ln in ledgerdomain_did_1["jsonl_path"].read_text().split("\n")
        if ln.strip()
    ]
    if len(lines) < 2:
        pytest.skip("fixture needs at least two documents")

    did = ledgerdomain_did_1["did"]
    known = len(lines[0].encode("utf-8"))
    suffix = "\n" + "\n".join(lines[1:])
    if trailing_newline:
        suffix += "\n"
    end = known + len(suffix.encode("utf-8")) - 1
    total = known + len(suffix.encode("utf-8"))
    real_url = parse_did(did).resolution_url()

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    local_store = SQLiteDIDDocStore(path)
    try:
        await local_store.add_did_documents([lines[0]], 0)
        respx.get(real_url).mock(
            return_value=Response(
                206,
                text=suffix,
                headers={"Content-Range": f"bytes {known}-{end}/{total}"},
            )
        )
        resolver = FullDIDResolver(local_store)
        # Plain DID forces a fetch even with a warm non-deactivated tip.
        result = await resolver.resolve(did)
        assert result.did_document is not None
        latest = await local_store.get_latest(did)
        assert latest is not None
        assert latest.version_id == len(lines) - 1
        expected_len = sum(len(ln.encode("utf-8")) for ln in lines) + (len(lines) - 1)
        assert latest.did_documents_jsonl_octet_length == expected_len
        assert respx.calls.last.request.headers["Range"] == f"bytes={known}-"
    finally:
        local_store.close()
        path.unlink(missing_ok=True)
