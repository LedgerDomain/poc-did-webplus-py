#!/usr/bin/env python3
"""HTTP server for the did-webplus test-vector catalog with harness control API."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

DOCUMENT_ROOT = Path("/srv")
CATALOG_URL_PREFIX = "did-webplus-spec/test-vector"
CATALOG_ROOT = DOCUMENT_ROOT / CATALOG_URL_PREFIX

DID_DOCUMENTS_JSONL = "did-documents.jsonl"
RESOLUTION_SCENARIO_JSON = "resolution-scenario.json"


def jsonl_line_end_octets(jsonl_bytes: bytes) -> list[int]:
    end_v: list[int] = []
    for i, byte in enumerate(jsonl_bytes):
        if byte == ord("\n"):
            end_v.append(i + 1)
    return end_v


class VectorBodies:
    __slots__ = (
        "jsonl_bytes",
        "did_document_count",
        "jsonl_line_end_octet_v",
    )

    def __init__(self, jsonl_bytes: bytes) -> None:
        self.jsonl_bytes = jsonl_bytes
        self.jsonl_line_end_octet_v = jsonl_line_end_octets(jsonl_bytes)
        self.did_document_count = len(self.jsonl_line_end_octet_v)

    def served_octet_length(self, served_did_document_count: int) -> int:
        if served_did_document_count <= 0 or not self.jsonl_line_end_octet_v:
            return 0
        index = min(
            served_did_document_count, len(self.jsonl_line_end_octet_v)
        )
        return self.jsonl_line_end_octet_v[index - 1]

    def served_body_bytes(self, served_did_document_count: int) -> bytes:
        length = self.served_octet_length(served_did_document_count)
        return self.jsonl_bytes[:length]


class VectorRuntime:
    __slots__ = (
        "default_served_did_document_count",
        "served_did_document_count",
        "jsonl_request_count",
    )

    def __init__(self, default_served_did_document_count: int) -> None:
        self.default_served_did_document_count = default_served_did_document_count
        self.served_did_document_count = default_served_did_document_count
        self.jsonl_request_count = 0

    def reset(self) -> None:
        self.served_did_document_count = self.default_served_did_document_count
        self.jsonl_request_count = 0


class CatalogState:
    def __init__(self, catalog_root: Path) -> None:
        self._lock = threading.Lock()
        self.bodies_m: dict[str, VectorBodies] = {}
        self.runtime_m: dict[str, VectorRuntime] = {}
        self._load_catalog(catalog_root)

    def _load_catalog(self, catalog_root: Path) -> None:
        if not catalog_root.is_dir():
            return
        for jsonl_path in sorted(catalog_root.rglob(DID_DOCUMENTS_JSONL)):
            rel_dir = jsonl_path.parent.relative_to(catalog_root)
            path_key = rel_dir.as_posix()
            if path_key == ".":
                continue
            jsonl_bytes = jsonl_path.read_bytes()
            bodies = VectorBodies(jsonl_bytes)
            self.bodies_m[path_key] = bodies
            self.runtime_m[path_key] = VectorRuntime(bodies.did_document_count)

    def set_serve_count(
        self, path_key: str, served_did_document_count: int
    ) -> tuple[int, int]:
        with self._lock:
            bodies = self.bodies_m.get(path_key)
            if bodies is None:
                raise KeyError(path_key)
            if served_did_document_count > bodies.did_document_count:
                raise ValueError(
                    f"servedDidDocumentCount {served_did_document_count} exceeds "
                    f"did document count {bodies.did_document_count}"
                )
            runtime = self.runtime_m[path_key]
            runtime.served_did_document_count = served_did_document_count
            octet_length = bodies.served_octet_length(served_did_document_count)
            return served_did_document_count, octet_length

    def request_count(self, path_key: str) -> int | None:
        with self._lock:
            runtime = self.runtime_m.get(path_key)
            if runtime is None:
                return None
            return runtime.jsonl_request_count

    def reset_all(self) -> None:
        with self._lock:
            for runtime in self.runtime_m.values():
                runtime.reset()

    def take_served_body_for_request(self, path_key: str) -> bytes | None:
        with self._lock:
            bodies = self.bodies_m.get(path_key)
            runtime = self.runtime_m.get(path_key)
            if bodies is None or runtime is None:
                return None
            runtime.jsonl_request_count += 1
            return bodies.served_body_bytes(runtime.served_did_document_count)


def normalize_control_path(path: str) -> str:
    return path.lstrip("/")


def split_dir_and_filename(url_path: str) -> tuple[str, str] | None:
    if "/" not in url_path:
        return None
    directory, filename = url_path.rsplit("/", 1)
    if not directory or not filename:
        return None
    return directory, filename


def catalog_relative_vector_path(url_path: str) -> str | None:
    prefix = CATALOG_URL_PREFIX + "/"
    if not url_path.startswith(prefix):
        return None
    rest = url_path[len(prefix) :]
    if not rest or rest.endswith("/"):
        return None
    return rest


def serve_did_documents_jsonl(
    handler: BaseHTTPRequestHandler, body_bytes: bytes, range_header: str | None
) -> None:
    length = len(body_bytes)

    if range_header is None:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/jsonl")
        handler.send_header("Content-Length", str(length))
        handler.end_headers()
        handler.wfile.write(body_bytes)
        return

    if not range_header.startswith("bytes="):
        handler.send_error(
            HTTPStatus.BAD_REQUEST, "Malformed Range header -- expected bytes="
        )
        return

    range_spec = range_header[6:].strip()
    if "," in range_spec:
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/jsonl")
        handler.send_header("Content-Length", str(length))
        handler.end_headers()
        handler.wfile.write(body_bytes)
        return

    if "-" not in range_spec:
        handler.send_error(
            HTTPStatus.BAD_REQUEST,
            "Malformed Range header -- expected bytes=START-END",
        )
        return

    start_str, end_str = range_spec.split("-", 1)

    if start_str == "":
        handler.send_response(HTTPStatus.OK)
        handler.send_header("Content-Type", "application/jsonl")
        handler.send_header("Content-Length", str(length))
        handler.end_headers()
        handler.wfile.write(body_bytes)
        return

    try:
        range_start = int(start_str)
    except ValueError:
        handler.send_error(
            HTTPStatus.BAD_REQUEST,
            "Malformed Range header -- could not parse start",
        )
        return

    if range_start < 0:
        handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        handler.send_header("Content-Range", f"bytes */{length}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return

    if range_start >= length:
        handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        handler.send_header("Content-Range", f"bytes */{length}")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return

    if end_str == "":
        slice_start = range_start
        slice_end = length
    else:
        try:
            range_end_inclusive = int(end_str)
        except ValueError:
            handler.send_error(
                HTTPStatus.BAD_REQUEST,
                "Malformed Range header -- could not parse end",
            )
            return
        if range_end_inclusive < range_start:
            handler.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            handler.send_header("Content-Range", f"bytes */{length}")
            handler.send_header("Content-Length", "0")
            handler.end_headers()
            return
        slice_start = range_start
        slice_end = min(range_end_inclusive + 1, length)

    suffix = body_bytes[slice_start:slice_end]
    end_inclusive = slice_start + len(suffix) - 1
    handler.send_response(HTTPStatus.PARTIAL_CONTENT)
    handler.send_header("Content-Type", "application/jsonl")
    handler.send_header(
        "Content-Range", f"bytes {slice_start}-{end_inclusive}/{length}"
    )
    handler.send_header("Content-Length", str(len(suffix)))
    handler.end_headers()
    handler.wfile.write(suffix)


def send_json(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_text(handler: BaseHTTPRequestHandler, status: int, message: str) -> None:
    body = message.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class TestVectorHTTPRequestHandler(BaseHTTPRequestHandler):
    catalog_state: CatalogState

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        url_path = unquote(parsed.path.lstrip("/"))

        if url_path == "health":
            send_json(
                self,
                HTTPStatus.OK,
                {
                    "ok": True,
                    "controlApi": True,
                    "server": "did-webplus-test-vector-server/1",
                },
            )
            return

        if url_path == "control/request-count":
            query = parse_qs(parsed.query)
            path_values = query.get("path")
            if not path_values:
                send_text(self, HTTPStatus.BAD_REQUEST, "missing path query parameter")
                return
            path_key = normalize_control_path(path_values[0])
            count_o = self.catalog_state.request_count(path_key)
            if count_o is None:
                send_text(
                    self,
                    HTTPStatus.NOT_FOUND,
                    f"vector path not found: {path_key}",
                )
                return
            send_json(
                self,
                HTTPStatus.OK,
                {"path": path_key, "requestCount": count_o},
            )
            return

        rel = catalog_relative_vector_path(url_path)
        if rel is not None and rel.endswith(f"/{DID_DOCUMENTS_JSONL}"):
            path_key = rel[: -len(DID_DOCUMENTS_JSONL) - 1]
            range_header = self.headers.get("Range")
            body_o = self.catalog_state.take_served_body_for_request(path_key)
            if body_o is None:
                send_text(self, HTTPStatus.NOT_FOUND, "vector not found")
                return
            serve_did_documents_jsonl(self, body_o, range_header)
            return

        file_path = (DOCUMENT_ROOT / url_path).resolve()
        try:
            file_path.relative_to(DOCUMENT_ROOT.resolve())
        except ValueError:
            send_text(self, HTTPStatus.NOT_FOUND, "not found")
            return
        if not file_path.is_file():
            send_text(self, HTTPStatus.NOT_FOUND, "not found")
            return

        if rel is not None:
            split = split_dir_and_filename(rel)
            if split is not None:
                vector_path, filename = split
                if filename == RESOLUTION_SCENARIO_JSON:
                    if not file_path.is_file():
                        send_text(
                            self,
                            HTTPStatus.NOT_FOUND,
                            "resolution-scenario.json not present for this vector",
                        )
                        return

        content = file_path.read_bytes()
        content_type, _ = mimetypes.guess_type(str(file_path))
        if content_type is None:
            if file_path.suffix == ".jsonl":
                content_type = "application/jsonl"
            elif file_path.suffix == ".json":
                content_type = "application/json"
            else:
                content_type = "application/octet-stream"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        url_path = unquote(parsed.path.lstrip("/"))
        if url_path != "control/serve-count":
            send_text(self, HTTPStatus.NOT_FOUND, "not found")
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            send_text(self, HTTPStatus.BAD_REQUEST, "invalid JSON body")
            return

        path_raw = payload.get("path")
        count_raw = payload.get("servedDidDocumentCount")
        if not isinstance(path_raw, str) or not isinstance(count_raw, int):
            send_text(
                self,
                HTTPStatus.BAD_REQUEST,
                "body requires path (string) and servedDidDocumentCount (integer)",
            )
            return

        path_key = normalize_control_path(path_raw)
        try:
            served_count, octet_length = self.catalog_state.set_serve_count(
                path_key, count_raw
            )
        except KeyError:
            send_text(
                self,
                HTTPStatus.NOT_FOUND,
                f"vector path not found: {path_key}",
            )
            return
        except ValueError as error:
            send_text(self, HTTPStatus.BAD_REQUEST, str(error))
            return

        send_json(
            self,
            HTTPStatus.OK,
            {
                "path": path_key,
                "servedDidDocumentCount": served_count,
                "servedOctetLength": octet_length,
            },
        )

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        url_path = unquote(parsed.path.lstrip("/"))
        if url_path != "control/reset":
            send_text(self, HTTPStatus.NOT_FOUND, "not found")
            return
        self.catalog_state.reset_all()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve did-webplus test-vector catalog")
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=int(os.environ.get("PORT", "80")),
        help="TCP port (default: 80 or $PORT)",
    )
    args = parser.parse_args()

    catalog_state = CatalogState(CATALOG_ROOT)
    TestVectorHTTPRequestHandler.catalog_state = catalog_state

    server = ThreadingHTTPServer(("", args.port), TestVectorHTTPRequestHandler)
    print(
        f"test_vector_server: catalog={CATALOG_ROOT} vectors={len(catalog_state.bodies_m)} port={args.port}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
