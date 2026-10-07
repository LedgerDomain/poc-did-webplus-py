"""HTTP client for fetching did-documents.jsonl from VDR or VDG."""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

import httpx

from did_webplus.did import parse_did

logger = logging.getLogger(__name__)

_CONTENT_RANGE_PARTIAL_RE = re.compile(
    r"^bytes\s+(\d+)-(\d+)/(\d+|\*)\s*$",
    re.IGNORECASE,
)


class HTTPClientError(Exception):
    """HTTP fetch error."""


def _parse_416_total(content_range: str | None) -> int | None:
    """Parse total length from ``Content-Range: bytes */N``."""
    if not content_range:
        return None
    prefix = "bytes */"
    if not content_range.startswith(prefix):
        return None
    try:
        return int(content_range[len(prefix) :].strip())
    except ValueError:
        return None


def _parse_206_content_range(
    content_range: str | None,
) -> tuple[int, int, int | None] | None:
    """
    Parse ``Content-Range: bytes START-END/TOTAL`` (TOTAL may be ``*``).

    Returns ``(start, end, total_or_None)`` or ``None`` if malformed.
    """
    if not content_range:
        return None
    match = _CONTENT_RANGE_PARTIAL_RE.match(content_range.strip())
    if match is None:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    total_s = match.group(3)
    total = None if total_s == "*" else int(total_s)
    return start, end, total


async def fetch_did_documents_jsonl(
    did: str,
    known_octet_length: int = 0,
    vdg_base_url: str | None = None,
    http_scheme_overrides: dict[str, str] | None = None,
) -> str:
    """
    Fetch updates to did-documents.jsonl for a DID.

    Uses ``Range: bytes=N-`` for both HTTP and HTTPS when a verified prefix
    exists (``known_octet_length > 0``). Cold stores use an ordinary GET.

    Status handling:
    - ``200``: accepted only when no Range was sent (full body expected).
    - ``206``: accepted for ranged requests; Content-Range start must match N.
    - ``416`` with ``Content-Range: bytes */N`` matching known length: up-to-date.
    - Any other status / range inconsistency: ``HTTPClientError``.
    """
    components = parse_did(did)
    if vdg_base_url:
        url = _vdg_url(vdg_base_url, did)
        logger.debug("http_client: fetching from VDG url=%s did=%s", url, did)
    else:
        url = components.resolution_url(http_scheme_overrides=http_scheme_overrides)
        logger.debug("http_client: fetching from VDR url=%s did=%s", url, did)

    range_requested = known_octet_length > 0
    headers: dict[str, str] = {}
    if range_requested:
        headers["Range"] = f"bytes={known_octet_length}-"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as e:
        raise HTTPClientError(f"transport error fetching {url}: {e}") from e

    if response.status_code == 200:
        if range_requested:
            raise HTTPClientError(
                f"unexpected HTTP 200 for ranged request to {url}; "
                "server ignored Range (refusing full-body re-ingestion)"
            )
        logger.debug(
            "http_client: got 200 len=%d from %s",
            len(response.text),
            url,
        )
        return response.text

    if response.status_code == 206:
        if not range_requested:
            raise HTTPClientError(
                f"unexpected HTTP 206 without Range request for {url}"
            )
        parsed = _parse_206_content_range(response.headers.get("Content-Range"))
        if parsed is None:
            raise HTTPClientError(
                f"206 missing or malformed Content-Range for {url}: "
                f"{response.headers.get('Content-Range')!r}"
            )
        start, end, total = parsed
        if start != known_octet_length:
            raise HTTPClientError(
                f"206 Content-Range start {start} != known_octet_length "
                f"{known_octet_length} for {url}"
            )
        if end < start:
            raise HTTPClientError(
                f"206 Content-Range end {end} < start {start} for {url}"
            )
        if total is not None and total <= start:
            raise HTTPClientError(
                f"206 Content-Range total {total} inconsistent with start "
                f"{start} for {url}"
            )
        logger.debug(
            "http_client: got 206 len=%d range=%s-%s/%s from %s",
            len(response.text),
            start,
            end,
            total if total is not None else "*",
            url,
        )
        return response.text

    if response.status_code == 416:
        content_range = response.headers.get("Content-Range")
        total = _parse_416_total(content_range)
        if total is not None and total == known_octet_length:
            return ""
        raise HTTPClientError(
            f"416 Range Not Satisfiable: Content-Range={content_range!r}, "
            f"known_octet_length={known_octet_length}"
        )

    logger.error(
        "http_client: HTTP %s for %s: %s",
        response.status_code,
        url,
        response.text,
    )
    raise HTTPClientError(
        f"HTTP {response.status_code} for {url}: {response.text!r}"
    )


def _vdg_url(vdg_base_url: str, did: str) -> str:
    """Build VDG fetch URL per Rust http.rs. DID must be URL-encoded in path."""
    base = vdg_base_url.rstrip("/")
    encoded_did = quote(did, safe="")
    return f"{base}/webplus/v1/fetch/{encoded_did}/did-documents.jsonl"
