"""Tests for HTTP client."""

import pytest
import respx
from httpx import Response

from did_webplus.http_client import fetch_did_documents_jsonl, HTTPClientError


@respx.mock
@pytest.mark.asyncio
async def test_fetch_full_content() -> None:
    did = "did:webplus:example.com:abc123"
    url = "https://example.com/abc123/did-documents.jsonl"
    content = '{"id":"did:webplus:example.com:abc123","selfHash":"E1"}\n'
    respx.get(url).mock(return_value=Response(200, text=content))
    result = await fetch_did_documents_jsonl(did)
    assert result == content
    assert respx.calls.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_fetch_with_range() -> None:
    did = "did:webplus:example.com:abc123"
    url = "http://example.com/abc123/did-documents.jsonl"
    respx.get(url).mock(return_value=Response(206, text="new content"))
    result = await fetch_did_documents_jsonl(
        did,
        known_octet_length=100,
        http_scheme_overrides={"example.com": "http"},
    )
    assert "Range" in respx.calls.last.request.headers
    assert respx.calls.last.request.headers["Range"] == "bytes=100-"


@respx.mock
@pytest.mark.asyncio
async def test_fetch_416_up_to_date() -> None:
    did = "did:webplus:example.com:abc123"
    url = "http://example.com/abc123/did-documents.jsonl"
    respx.get(url).mock(
        return_value=Response(
            416,
            headers={"Content-Range": "bytes */50"},
        )
    )
    result = await fetch_did_documents_jsonl(
        did,
        known_octet_length=50,
        http_scheme_overrides={"example.com": "http"},
    )
    assert result == ""


@respx.mock
@pytest.mark.asyncio
async def test_fetch_416_mismatch_raises() -> None:
    did = "did:webplus:example.com:abc123"
    url = "http://example.com/abc123/did-documents.jsonl"
    respx.get(url).mock(
        return_value=Response(
            416,
            headers={"Content-Range": "bytes */100"},
        )
    )
    with pytest.raises(HTTPClientError):
        await fetch_did_documents_jsonl(
            did,
            known_octet_length=50,
            http_scheme_overrides={"example.com": "http"},
        )


@respx.mock
@pytest.mark.asyncio
async def test_fetch_vdg_url() -> None:
    did = "did:webplus:example.com:abc123"
    vdg_url = "https://vdg.example.com/webplus/v1/fetch/did:webplus:example.com:abc123/did-documents.jsonl"
    respx.get(vdg_url).mock(return_value=Response(200, text=""))
    await fetch_did_documents_jsonl(did, vdg_base_url="https://vdg.example.com")
    assert respx.calls.last.request.url.path == "/webplus/v1/fetch/did:webplus:example.com:abc123/did-documents.jsonl"
