"""HTTP client for fetching did-documents.jsonl from VDR or VDG."""

from __future__ import annotations

import httpx

from did_webplus.did import parse_did


class HTTPClientError(Exception):
    """HTTP fetch error."""


async def fetch_did_documents_jsonl(
    did: str,
    known_octet_length: int = 0,
    vdg_base_url: str | None = None,
) -> str:
    """
    Fetch updates to did-documents.jsonl for a DID.

    Uses Range request if known_octet_length > 0.
    Returns the new content (empty string if up-to-date).

    Args:
        did: The DID (without query params)
        known_octet_length: Bytes already known (for Range request)
        vdg_base_url: If set, fetch from VDG instead of VDR

    Returns:
        New content (may be empty if 416 and Content-Range matches)
    """
    components = parse_did(did)
    if vdg_base_url:
        url = _vdg_url(vdg_base_url, did)
    else:
        url = components.resolution_url()

    headers: dict[str, str] = {}
    if known_octet_length > 0:
        headers["Range"] = f"bytes={known_octet_length}-"

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)

    if response.status_code in (200, 206):
        return response.text

    if response.status_code == 416:
        content_range = response.headers.get("Content-Range")
        if content_range and content_range.startswith("bytes */"):
            total = int(content_range[8:].strip())
            if total == known_octet_length:
                return ""
        raise HTTPClientError(
            f"416 Range Not Satisfiable: Content-Range={content_range!r}, "
            f"known_octet_length={known_octet_length}"
        )

    raise HTTPClientError(
        f"HTTP {response.status_code} for {url}: {response.text[:200]!r}"
    )


def _vdg_url(vdg_base_url: str, did: str) -> str:
    """Build VDG fetch URL per Rust http.rs."""
    base = vdg_base_url.rstrip("/")
    return f"{base}/webplus/v1/fetch/{did}/did-documents.jsonl"
