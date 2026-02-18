"""DID parsing and URL mapping for did:webplus."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, unquote

PREFIX = "did:webplus:"


class DIDError(Exception):
    """Base exception for DID parsing errors."""


class MalformedDIDError(DIDError):
    """DID string is malformed."""


@dataclass(frozen=True)
class DIDComponents:
    """Parsed components of a did:webplus DID."""

    host: str
    port: int | None
    path: str | None
    root_self_hash: str

    def hostname(self) -> str:
        """Host part for scheme determination (localhost vs other)."""
        return self.host.lower()

    def resolution_url(self, *, use_https: bool | None = None) -> str:
        """
        Produce the resolution URL for this DID's did-documents.jsonl.

        Args:
            use_https: If True, force https. If False, force http. If None, use
                https for non-localhost and http for localhost.
        """
        if use_https is None:
            use_https = self.hostname() != "localhost"
        scheme = "https" if use_https else "http"
        host_part = self.host
        if self.port is not None:
            host_part = f"{self.host}:{self.port}"
        path_parts: list[str] = []
        if self.path:
            path_parts.extend(self.path.split(":"))
        path_parts.append(self.root_self_hash)
        path_parts.append("did-documents.jsonl")
        path_str = "/".join(path_parts)
        return f"{scheme}://{host_part}/{path_str}"


@dataclass(frozen=True)
class DIDWithQuery:
    """DID with optional query parameters."""

    did: str
    query_self_hash: str | None
    query_version_id: int | None

    @property
    def has_query(self) -> bool:
        return self.query_self_hash is not None or self.query_version_id is not None


def parse_did(did_str: str) -> DIDComponents:
    """
    Parse a did:webplus DID (without query or fragment) into components.

    Raises:
        MalformedDIDError: If the DID is invalid.
    """
    if not did_str.startswith(PREFIX):
        raise MalformedDIDError(f"DID must start with {PREFIX!r}")
    rest = did_str[len(PREFIX) :]
    if "?" in rest:
        rest = rest.split("?")[0]
    if "#" in rest:
        raise MalformedDIDError("DID query must not contain a fragment")
    parts = rest.split(":")
    if len(parts) < 2:
        raise MalformedDIDError("DID must have at least host and root-self-hash")
    root_self_hash = parts[-1]
    host_part = parts[0]
    port: int | None = None
    path_parts: list[str] = []
    if "%3A" in host_part.upper():
        decoded = unquote(host_part)
        if ":" in decoded:
            host, port_str = decoded.split(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                raise MalformedDIDError(f"Invalid port in DID: {port_str!r}")
            host_part = host
        else:
            host_part = decoded
    host = host_part
    if len(parts) > 2:
        middle = parts[1:-1]
        for p in middle:
            path_parts.append(unquote(p) if "%" in p else p)
    path = ":".join(path_parts) if path_parts else None
    return DIDComponents(host=host, port=port, path=path, root_self_hash=root_self_hash)


def did_to_resolution_url(did_str: str, *, use_https: bool | None = None) -> str:
    """Convert a did:webplus DID to its resolution URL per spec."""
    parsed = parse_did_with_query(did_str)
    components = parse_did(parsed.did)
    return components.resolution_url(use_https=use_https)


def parse_did_with_query(did_query: str) -> DIDWithQuery:
    """
    Parse a DID URL that may include query parameters (?selfHash=...&versionId=...).

    Raises:
        MalformedDIDError: If the DID is invalid.
    """
    if "#" in did_query:
        raise MalformedDIDError("DID query must not contain a fragment")
    if "?" not in did_query:
        return DIDWithQuery(did=did_query, query_self_hash=None, query_version_id=None)
    did, query_string = did_query.split("?", 1)
    parse_did(did)
    params = parse_qs(query_string, strict_parsing=False)
    query_self_hash = None
    if "selfHash" in params and params["selfHash"]:
        query_self_hash = params["selfHash"][0]
    query_version_id = None
    if "versionId" in params and params["versionId"]:
        try:
            query_version_id = int(params["versionId"][0])
        except ValueError:
            raise MalformedDIDError(f"Invalid versionId in query: {params['versionId'][0]!r}")
    return DIDWithQuery(
        did=did,
        query_self_hash=query_self_hash,
        query_version_id=query_version_id,
    )


def did_to_resolution_url(did_str: str, *, use_https: bool | None = None) -> str:
    """
    Convert a did:webplus DID to its resolution URL per spec.

    Steps (per spec):
    1. Drop did:webplus: prefix
    2. Replace all : with /
    3. Percent-decode
    4. Append /did-documents.jsonl
    5. Prepend http:// for localhost, https:// otherwise
    """
    parsed = parse_did_with_query(did_str)
    components = parse_did(parsed.did)
    return components.resolution_url(use_https=use_https)
