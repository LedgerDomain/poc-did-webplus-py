"""Verifiable Data Registry (VDR) HTTP service for did:webplus."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Request, Response

from did_webplus.did import MalformedDIDError, parse_did
from did_webplus.document import parse_did_document
from did_webplus.selfhash import verify_self_hash
from did_webplus.store import DIDDocStore
from did_webplus.verification import VerificationError, verify_proofs

logger = logging.getLogger(__name__)


class VDRError(Exception):
    """VDR operation failed."""


@dataclass
class VDRConfig:
    """Configuration for the VDR service."""

    did_hostname: str
    did_port: int | None = None
    path_prefix: str | None = None
    vdg_base_urls: list[str] = ()
    store: DIDDocStore | None = None


def _path_to_did(path: str, hostname: str, port: int | None) -> str:
    """
    Convert request path to DID.

    Path format: /{path_segments}/{root_self_hash}/did-documents.jsonl
    e.g. /uHiA...C8A/did-documents.jsonl or /path1/path2/uHiA...C8A/did-documents.jsonl
    Host and port come from the request URL, not from the path.
    """
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        raise VDRError("Path must end with {root_self_hash}/did-documents.jsonl")
    if segments[-1] != "did-documents.jsonl":
        raise VDRError("Path must end with did-documents.jsonl")
    root_self_hash = segments[-2]
    path_components = segments[:-2]
    path_part = ":".join(path_components) if path_components else None

    host_part = hostname
    if port is not None:
        host_part = f"{hostname}%3A{port}"

    parts = [host_part]
    if path_part:
        parts.append(path_part)
    parts.append(root_self_hash)
    return f"did:webplus:{':'.join(parts)}"


def _did_matches_vdr_config(did: str, config: VDRConfig) -> bool:
    """Check if DID's domain/port/path match VDR config."""
    try:
        components = parse_did(did)
    except MalformedDIDError:
        return False
    if components.host.lower() != config.did_hostname.lower():
        return False
    if components.port != config.did_port:
        return False
    if config.path_prefix is not None and components.path != config.path_prefix:
        return False
    return True


def _validate_document(
    jcs_str: str,
    doc_dict: dict,
    prev_doc: dict | None,
) -> None:
    """Validate a single document (self-hash, chain, proofs) and raise if invalid."""
    verify_self_hash(jcs_str)
    doc = parse_did_document(jcs_str)
    prev = parse_did_document(json.dumps(prev_doc)) if prev_doc else None
    doc.verify_chain_constraints(prev)
    try:
        verify_proofs(doc_dict, prev_doc)
    except VerificationError as e:
        raise VDRError(f"Proof verification failed: {e}") from e


async def _notify_vdgs(did: str, vdg_base_urls: list[str]) -> None:
    """POST to each VDG to notify of DID update. Fire-and-forget."""
    encoded_did = quote(did, safe="")
    for base_url in vdg_base_urls:
        url = f"{base_url.rstrip('/')}/webplus/v1/update/{encoded_did}"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, timeout=5.0)
                if resp.status_code >= 400:
                    logger.warning("VDG notification failed: %s %s", url, resp.status_code)
        except Exception as e:
            logger.warning("VDG notification error for %s: %s", url, e)


def create_vdr_app(config: VDRConfig) -> FastAPI:
    """Create FastAPI app for the VDR service."""
    app = FastAPI(title="did:webplus VDR")

    @app.get("/health")
    async def health() -> Response:
        return Response(status_code=200)

    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT"],
    )
    async def did_documents(request: Request, path: str) -> Response:
        if not path.endswith("/did-documents.jsonl"):
            return Response(status_code=404)
        full_path = f"/{path}" if not path.startswith("/") else path

        host = request.url.hostname or config.did_hostname
        port = request.url.port if request.url.port and request.url.port not in (80, 443) else config.did_port

        try:
            did = _path_to_did(full_path, host, port)
        except VDRError as e:
            logger.debug("vdr: path_to_did failed path=%s: %s", full_path, e)
            return Response(content=str(e), status_code=400)

        logger.debug("vdr: %s %s -> did=%s", request.method, full_path, did)

        if not _did_matches_vdr_config(did, config):
            logger.warning(
                "vdr: did_matches_vdr_config failed did=%s hostname=%s port=%s",
                did,
                config.did_hostname,
                config.did_port,
            )
            return Response(
                content="DID domain/port/path does not match VDR configuration",
                status_code=403,
            )

        store = config.store
        if store is None:
            return Response(content="Store not configured", status_code=500)

        if request.method == "GET":
            return await _handle_get(did, request, store)
        if request.method == "POST":
            return await _handle_post(did, request, store, config)
        if request.method == "PUT":
            return await _handle_put(did, request, store, config)

        return Response(status_code=405)

    async def _handle_get(did: str, request: Request, store: DIDDocStore) -> Response:
        """Handle GET did-documents.jsonl with optional Range support."""
        total_length = await store.get_microledger_octet_length(did)
        if total_length == 0:
            logger.debug("vdr: GET 404 did=%s (empty)", did)
            return Response(status_code=404)

        range_header = request.headers.get("range")
        if range_header and range_header.startswith("bytes="):
            try:
                range_spec = range_header[6:].strip()
                if range_spec.endswith("-"):
                    start = int(range_spec[:-1])
                    if start < 0:
                        return Response(
                            headers={"Content-Range": f"bytes */{total_length}"},
                            status_code=416,
                        )
                    if start >= total_length:
                        return Response(
                            headers={"Content-Range": f"bytes */{total_length}"},
                            status_code=416,
                        )
                    content = await store.get_microledger_from_byte_offset(did, start)
                    return Response(
                        content=content,
                        status_code=206,
                        headers={
                            "Content-Range": f"bytes {start}-{total_length - 1}/{total_length}",
                            "Content-Type": "application/x-ndjson",
                        },
                    )
            except ValueError:
                pass

        content = await store.get_microledger_jsonl(did)
        logger.debug("vdr: GET 200 did=%s len=%d", did, len(content))
        return Response(
            content=content,
            headers={
                "Content-Type": "application/x-ndjson",
                "Content-Length": str(len(content.encode("utf-8"))),
            },
        )

    async def _handle_post(
        did: str, request: Request, store: DIDDocStore, cfg: VDRConfig
    ) -> Response:
        """Handle POST (DID create - root document)."""
        try:
            body = await request.body()
            jcs_str = body.decode("utf-8").strip()
        except Exception as e:
            return Response(content=f"Invalid body: {e}", status_code=400)

        try:
            doc_dict = json.loads(jcs_str)
        except json.JSONDecodeError as e:
            return Response(content=f"Invalid JSON: {e}", status_code=400)

        if doc_dict.get("versionId") != 0 or doc_dict.get("prevDIDDocumentSelfHash") is not None:
            return Response(
                content="Root document must have versionId 0 and no prevDIDDocumentSelfHash",
                status_code=400,
            )

        if doc_dict.get("id") != did:
            return Response(
                content=f"Document id {doc_dict.get('id')!r} does not match DID {did!r}",
                status_code=400,
            )

        try:
            _validate_document(jcs_str, doc_dict, None)
        except VDRError as e:
            logger.warning("vdr: POST validation failed did=%s: %s", did, e)
            return Response(content=str(e), status_code=400)
        except Exception as e:
            logger.exception("vdr: POST validation error did=%s", did)
            return Response(content=str(e), status_code=400)

        logger.info(
            "vdr: POST create did=%s selfHash=%s versionId=0",
            did,
            doc_dict.get("selfHash"),
        )
        await store.add_did_documents([jcs_str], 0)

        if cfg.vdg_base_urls:
            asyncio.create_task(_notify_vdgs(did, cfg.vdg_base_urls))

        return Response(status_code=200)

    async def _handle_put(
        did: str, request: Request, store: DIDDocStore, cfg: VDRConfig
    ) -> Response:
        """Handle PUT (DID update - non-root document)."""
        try:
            body = await request.body()
            jcs_str = body.decode("utf-8").strip()
        except Exception as e:
            return Response(content=f"Invalid body: {e}", status_code=400)

        try:
            doc_dict = json.loads(jcs_str)
        except json.JSONDecodeError as e:
            return Response(content=f"Invalid JSON: {e}", status_code=400)

        if doc_dict.get("versionId") == 0 or doc_dict.get("prevDIDDocumentSelfHash") is None:
            return Response(
                content="Update document must have versionId > 0 and prevDIDDocumentSelfHash",
                status_code=400,
            )

        if doc_dict.get("id") != did:
            return Response(
                content=f"Document id {doc_dict.get('id')!r} does not match DID {did!r}",
                status_code=400,
            )

        prev_hash = doc_dict.get("prevDIDDocumentSelfHash")
        prev_record = await store.get_by_self_hash(did, prev_hash)
        if prev_record is None:
            return Response(
                content="Previous DID document not found",
                status_code=400,
            )
        prev_doc = json.loads(prev_record.did_document_jcs)

        try:
            _validate_document(jcs_str, doc_dict, prev_doc)
        except VDRError as e:
            logger.warning(
                "vdr: PUT validation failed did=%s versionId=%s: %s",
                did,
                doc_dict.get("versionId"),
                e,
            )
            return Response(content=str(e), status_code=400)
        except Exception as e:
            logger.exception("vdr: PUT validation error did=%s", did)
            return Response(content=str(e), status_code=400)

        logger.info(
            "vdr: PUT update did=%s selfHash=%s versionId=%s",
            did,
            doc_dict.get("selfHash"),
            doc_dict.get("versionId"),
        )
        known_length = prev_record.did_documents_jsonl_octet_length
        await store.add_did_documents([jcs_str], known_length)

        if cfg.vdg_base_urls:
            asyncio.create_task(_notify_vdgs(did, cfg.vdg_base_urls))

        return Response(status_code=200)

    return app
