#!/usr/bin/env python3
"""
Resolve did:webplus catalog test vectors with Python, Rust, and Zkred resolvers.

Fetches index.json and per-vector test-vector.json over HTTP, applies the
resolve-latest oracle from each vector's expected.valid / didDocumentCount,
and reports PASS/FAIL with a per-resolver report (totals, by group, failures).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

from resolvers import (
    HTTP_SCHEME_OVERRIDE,
    ResolutionOptions,
    ResolveResult,
    ResolverKind,
    resolve,
)

INDEX_FORMAT = "did-webplus-test-vector-index/2"
VECTOR_FORMAT = "did-webplus-test-vector/1"
DEFAULT_CATALOG_URL = "http://ledgerdomain.github.io/did-webplus-spec/test-vector"
RESOLVER_CHOICES = ("python", "rust", "zkred")
SUITE_ID = "vectors"
CaseStatus = Literal["pass", "fail", "error", "timeout"]

logger = logging.getLogger("interop.test_vectors")

os.environ.setdefault("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE", HTTP_SCHEME_OVERRIDE)


@dataclass(frozen=True)
class VectorMeta:
    """Catalog entry plus fetched test-vector.json fields needed for the oracle."""

    name: str
    path: str
    did: str
    group_v: tuple[str, ...]
    did_document_count: int
    valid: bool
    valid_did_document_count: int | None
    error_code: str | None
    error_version_id: int | None


@dataclass(frozen=True)
class CaseResult:
    """One (vector, resolver) oracle evaluation."""

    name: str
    group_v: tuple[str, ...]
    resolver: str
    ok: bool
    detail: str
    status: CaseStatus
    unsupported_options: tuple[str, ...] = ()


def _http_get_json(url: str, timeout: float) -> Any:
    """GET URL and parse JSON body; raise on HTTP or decode errors."""
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {url} failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"GET {url} failed: {e.reason}") from e
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GET {url}: invalid JSON: {e}") from e


def _catalog_join(catalog_url: str, *parts: str) -> str:
    """Join catalog base URL with path segments (no leading slash on parts)."""
    base = catalog_url if catalog_url.endswith("/") else catalog_url + "/"
    return urljoin(base, "/".join(parts))


def _fetch_index(catalog_url: str, timeout: float) -> dict[str, Any]:
    """Fetch and validate the test-vector index document."""
    url = _catalog_join(catalog_url, "index.json")
    data = _http_get_json(url, timeout)
    fmt = data.get("format")
    if fmt != INDEX_FORMAT:
        raise RuntimeError(
            f"index.json format {fmt!r} != expected {INDEX_FORMAT!r}"
        )
    if not isinstance(data.get("vectors"), dict):
        raise RuntimeError("index.json missing 'vectors' object")
    if not isinstance(data.get("groups"), dict):
        raise RuntimeError("index.json missing 'groups' object")
    return data


def _groups_for_vector(groups: dict[str, Any]) -> dict[str, list[str]]:
    """Build name -> list of group names from index groups map."""
    name_to_group_v: dict[str, list[str]] = defaultdict(list)
    for group_name, member_v in groups.items():
        if not isinstance(member_v, list):
            continue
        for name in member_v:
            if isinstance(name, str):
                name_to_group_v[name].append(group_name)
    return dict(name_to_group_v)


def _select_vector_names(
    index: dict[str, Any],
    group_filter_v: list[str],
    name_filter_v: list[str],
) -> list[str]:
    """Select vector names from --group / --name filters (union); default all."""
    vectors: dict[str, Any] = index["vectors"]
    groups: dict[str, Any] = index["groups"]

    if not group_filter_v and not name_filter_v:
        return sorted(vectors.keys())

    selected_s: set[str] = set()
    for group_name in group_filter_v:
        if group_name not in groups:
            raise RuntimeError(f"unknown group {group_name!r}")
        member_v = groups[group_name]
        if not isinstance(member_v, list):
            raise RuntimeError(f"group {group_name!r} is not a list")
        selected_s.update(member_v)
    for name in name_filter_v:
        if name not in vectors:
            raise RuntimeError(f"unknown vector name {name!r}")
        selected_s.add(name)

    unknown_s = selected_s - set(vectors.keys())
    if unknown_s:
        raise RuntimeError(f"group members missing from vectors: {sorted(unknown_s)}")
    return sorted(selected_s)


def _fetch_vector_meta(
    catalog_url: str,
    name: str,
    index_entry: dict[str, Any],
    group_v: list[str],
    timeout: float,
) -> VectorMeta:
    """Fetch test-vector.json for one index entry and validate against the index."""
    path = index_entry.get("path")
    index_did = index_entry.get("did")
    if not isinstance(path, str) or not path:
        raise RuntimeError(f"vector {name!r}: index entry missing path")
    if not isinstance(index_did, str) or not index_did:
        raise RuntimeError(f"vector {name!r}: index entry missing did")

    url = _catalog_join(catalog_url, path, "test-vector.json")
    data = _http_get_json(url, timeout)
    fmt = data.get("format")
    if fmt != VECTOR_FORMAT:
        raise RuntimeError(
            f"vector {name!r}: format {fmt!r} != expected {VECTOR_FORMAT!r}"
        )
    did = data.get("did")
    if did != index_did:
        raise RuntimeError(
            f"vector {name!r}: did mismatch index={index_did!r} vector={did!r}"
        )
    tv_name = data.get("name")
    if tv_name is not None and tv_name != name:
        raise RuntimeError(
            f"vector {name!r}: name field {tv_name!r} != index key"
        )

    n = data.get("didDocumentCount")
    if not isinstance(n, int):
        raise RuntimeError(f"vector {name!r}: didDocumentCount must be int")
    expected = data.get("expected")
    if not isinstance(expected, dict):
        raise RuntimeError(f"vector {name!r}: missing expected object")
    valid = expected.get("valid")
    if not isinstance(valid, bool):
        raise RuntimeError(f"vector {name!r}: expected.valid must be bool")
    k = expected.get("validDidDocumentCount")
    if k is not None and not isinstance(k, int):
        raise RuntimeError(
            f"vector {name!r}: expected.validDidDocumentCount must be int"
        )
    error_code = expected.get("errorCode")
    if error_code is not None and not isinstance(error_code, str):
        raise RuntimeError(f"vector {name!r}: expected.errorCode must be str")
    error_version_id = expected.get("errorVersionId")
    if error_version_id is not None and not isinstance(error_version_id, int):
        raise RuntimeError(
            f"vector {name!r}: expected.errorVersionId must be int"
        )

    return VectorMeta(
        name=name,
        path=path,
        did=did,
        group_v=tuple(group_v),
        did_document_count=n,
        valid=valid,
        valid_did_document_count=k,
        error_code=error_code,
        error_version_id=error_version_id,
    )


def _resolve_outcome(
    result: ResolveResult,
) -> tuple[bool, int | None, str]:
    """Map adapter result to oracle inputs (succeeded, versionId, detail)."""
    detail_parts: list[str] = []
    if result.unsupported_options:
        detail_parts.append(
            f"unsupported options: {', '.join(result.unsupported_options)}"
        )
    if result.returncode != 0:
        detail_parts.append("resolve exited non-zero")
        return False, None, "; ".join(detail_parts) or "resolve exited non-zero"
    if result.parse_error:
        detail_parts.append(result.parse_error)
        return False, None, "; ".join(detail_parts)
    if not result.did_document:
        detail_parts.append("no didDocument in result")
        return False, None, "; ".join(detail_parts)
    vid = result.did_document.get("versionId")
    if detail_parts:
        return True, vid, "; ".join(detail_parts)
    return True, vid, "ok"


def _run_resolver(
    resolver: ResolverKind,
    did: str,
    *,
    timeout: float,
) -> ResolveResult:
    """Invoke unified adapter; each case gets a fresh persistent store mount."""
    prefix = f"tv-{resolver[:2]}-"
    with tempfile.TemporaryDirectory(prefix=prefix) as store_dir:
        return resolve(
            resolver,  # ResolverKind; validated by RESOLVER_CHOICES
            did,
            options=ResolutionOptions(),
            store_dir=store_dir,
            timeout=timeout,
        )


def _evaluate_oracle(
    meta: VectorMeta,
    resolve_ok: bool,
    version_id_o: int | None,
) -> tuple[bool, str]:
    """Apply resolve-latest oracle; errorCode / errorVersionId / k are advisory."""
    n = meta.did_document_count
    k = meta.valid_did_document_count
    if meta.error_code is not None or meta.error_version_id is not None:
        logger.info(
            "advisory %s: errorCode=%s errorVersionId=%s",
            meta.name,
            meta.error_code,
            meta.error_version_id,
        )
    if k is not None:
        logger.debug("advisory %s: validDidDocumentCount(k)=%s", meta.name, k)

    # n==0 special-case before valid (jsonl-empty-file is valid:true but unresolvable)
    if n == 0:
        if resolve_ok:
            return False, "n==0: resolve must fail, but succeeded"
        return True, "n==0: resolve failed as expected"

    if meta.valid:
        expected_vid = n - 1
        if not resolve_ok:
            return (
                False,
                f"valid==true: resolve must succeed with versionId={expected_vid}, but failed",
            )
        if version_id_o != expected_vid:
            return (
                False,
                f"valid==true: expected versionId={expected_vid}, got {version_id_o!r}",
            )
        return True, f"valid==true: versionId={expected_vid}"

    if resolve_ok:
        return (
            False,
            f"valid==false: resolve must fail, but succeeded with versionId={version_id_o!r}",
        )
    return True, "valid==false: resolve failed as expected"


def _run_case(meta: VectorMeta, resolver: str, timeout: float) -> CaseResult:
    """Resolve one vector with one resolver and evaluate the oracle."""
    unsupported_v: tuple[str, ...] = ()
    status: CaseStatus = "pass"
    try:
        result = _run_resolver(resolver, meta.did, timeout=timeout)
        unsupported_v = tuple(result.unsupported_options or ())
        resolve_ok, version_id_o, parse_detail = _resolve_outcome(result)
        if not resolve_ok and parse_detail != "resolve exited non-zero":
            logger.debug(
                "%s/%s parse: %s", meta.name, resolver, parse_detail
            )
        ok, detail = _evaluate_oracle(meta, resolve_ok, version_id_o)
        if not resolve_ok and parse_detail != "resolve exited non-zero":
            detail = f"{detail} ({parse_detail})"
        status = "pass" if ok else "fail"
    except subprocess.TimeoutExpired:
        # Timeout counts as resolve failure for the oracle.
        ok, detail = _evaluate_oracle(meta, False, None)
        detail = f"resolver timed out after {timeout}s; {detail}"
        status = "timeout"
    except Exception as e:
        ok, detail = False, f"harness error: {e}"
        status = "error"

    return CaseResult(
        name=meta.name,
        group_v=meta.group_v,
        resolver=resolver,
        ok=ok,
        detail=detail,
        status=status,
        unsupported_options=unsupported_v,
    )


def _case_to_json(case: CaseResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": case.name,
        "resolver": case.resolver,
        "ok": case.ok,
        "status": case.status,
        "detail": case.detail,
    }
    if case.unsupported_options:
        payload["unsupported_options"] = list(case.unsupported_options)
    return payload


def _write_suite_artifact(
    path: Path,
    *,
    config: dict[str, Any],
    cases: list[CaseResult],
    expected: int,
    executed: int,
    expected_by_resolver_m: dict[str, int],
    duration_seconds: float,
    runner_exit_code: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "suite": SUITE_ID,
        "kind": "vectors",
        "config": config,
        "expected": expected,
        "executed": executed,
        "expectedByResolver": expected_by_resolver_m,
        "cases": [_case_to_json(c) for c in cases],
        "durationSeconds": round(duration_seconds, 3),
        "runnerExitCode": runner_exit_code,
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _print_summary(result_v: list[CaseResult]) -> None:
    """Print one report per resolver: totals, by-group tallies, and failures."""
    by_resolver: dict[str, list[CaseResult]] = defaultdict(list)
    for r in result_v:
        by_resolver[r.resolver].append(r)

    for resolver in sorted(by_resolver):
        cases = by_resolver[resolver]
        passed = sum(1 for c in cases if c.ok)
        print(f"\n=== {resolver} ===")
        print(f"  {passed}/{len(cases)} passed")

        by_group: dict[str, list[CaseResult]] = defaultdict(list)
        for c in cases:
            if c.group_v:
                for g in c.group_v:
                    by_group[g].append(c)
            else:
                by_group["(ungrouped)"].append(c)

        print("\n  --- Summary by group ---")
        for group in sorted(by_group):
            group_cases = by_group[group]
            group_passed = sum(1 for c in group_cases if c.ok)
            print(f"    {group}: {group_passed}/{len(group_cases)} passed")

        fail_v = [c for c in cases if not c.ok]
        print(f"\n  --- Failures ({len(fail_v)}) ---")
        if not fail_v:
            print("    (none)")
        else:
            for c in fail_v:
                print(f"    FAIL {c.name}: {c.detail}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run did:webplus test-vector catalog against interop resolvers.",
    )
    parser.add_argument(
        "--resolver",
        choices=(*RESOLVER_CHOICES, "all"),
        default="all",
        help="Resolver under test (default: all)",
    )
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        metavar="NAME",
        help="Include vectors from this index group (repeatable)",
    )
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="NAME",
        help="Include this vector by name (repeatable)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=8,
        metavar="N",
        help="ThreadPoolExecutor worker count (default: 8)",
    )
    parser.add_argument(
        "--catalog-url",
        default=DEFAULT_CATALOG_URL,
        help=f"Catalog base URL (default: {DEFAULT_CATALOG_URL})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Per-resolve timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--report-json",
        metavar="PATH",
        default=None,
        help="Write machine-readable suite artifact to PATH",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report_path_o = Path(args.report_json) if args.report_json else None
    config_m = {k: v for k, v in vars(args).items() if k != "report_json"}
    t0 = time.monotonic()
    runner_exit = 2
    result_v: list[CaseResult] = []
    expected = 0
    executed = 0
    expected_by_resolver_m: dict[str, int] = {}

    try:
        if args.jobs < 1:
            print("--jobs must be >= 1", file=sys.stderr)
            return runner_exit

        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )

        resolver_v = (
            list(RESOLVER_CHOICES) if args.resolver == "all" else [args.resolver]
        )

        try:
            index = _fetch_index(args.catalog_url, args.timeout)
            name_v = _select_vector_names(index, args.group, args.name)
            name_to_group_v = _groups_for_vector(index["groups"])
            meta_v: list[VectorMeta] = []
            for name in name_v:
                meta_v.append(
                    _fetch_vector_meta(
                        args.catalog_url,
                        name,
                        index["vectors"][name],
                        name_to_group_v.get(name, []),
                        args.timeout,
                    )
                )
        except RuntimeError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return runner_exit

        jobs = [(meta, resolver) for meta in meta_v for resolver in resolver_v]
        expected = len(jobs)
        expected_by_resolver_m = {r: len(meta_v) for r in resolver_v}

        print(
            f"Running {len(meta_v)} vector(s) × {len(resolver_v)} resolver(s) "
            f"with jobs={args.jobs}, timeout={args.timeout}s"
        )

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            future_m = {
                pool.submit(_run_case, meta, resolver, args.timeout): (
                    meta.name,
                    resolver,
                )
                for meta, resolver in jobs
            }
            for future in concurrent.futures.as_completed(future_m):
                case = future.result()
                status = "PASS" if case.ok else "FAIL"
                line = f"{status} {case.resolver} {case.name}"
                if not case.ok:
                    line = f"{line}: {case.detail}"
                print(line, flush=True)
                result_v.append(case)

        executed = len(result_v)
        result_v.sort(key=lambda c: (c.name, c.resolver))
        _print_summary(result_v)

        failed = sum(1 for c in result_v if not c.ok)
        total = len(result_v)
        print(f"\n=== {total - failed}/{total} passed ===")
        runner_exit = 1 if failed else 0
        return runner_exit
    finally:
        if report_path_o is not None:
            cases_sorted_v = sorted(result_v, key=lambda c: (c.name, c.resolver))
            _write_suite_artifact(
                report_path_o,
                config=config_m,
                cases=cases_sorted_v,
                expected=expected,
                executed=executed,
                expected_by_resolver_m=expected_by_resolver_m,
                duration_seconds=time.monotonic() - t0,
                runner_exit_code=runner_exit,
            )


if __name__ == "__main__":
    sys.exit(main())
