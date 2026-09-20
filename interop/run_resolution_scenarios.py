#!/usr/bin/env python3
"""
Run did:webplus resolution-scenario catalog vectors against interop resolvers.

Fetches index.json and per-vector resolution-scenario.json, drives the catalog
server control API (serve-count truncation and request counters) per step,
resolves with persistent per-scenario store, and asserts normative expectations.
"""

from __future__ import annotations

import argparse
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
from typing import Any, Callable, Literal, TypeVar
from urllib.parse import urlencode, urlparse

from resolvers import (
    HTTP_SCHEME_OVERRIDE,
    ResolutionOptions,
    ResolveResult,
    ResolverKind,
    resolve,
)

from run_test_vectors import (
    DEFAULT_CATALOG_URL,
    RESOLVER_CHOICES,
    _catalog_join,
    _fetch_index,
    _http_get_json,
    _select_vector_names,
)

SCENARIO_FORMAT = "did-webplus-resolution-scenario/1"
RESOLUTION_SCENARIO_GROUP = "resolution-scenario"
SUITE_ID = "scenarios"
CaseStatus = Literal["pass", "fail", "error", "timeout"]

NORMATIVE_RESOLUTION_METADATA_KEYS = (
    "fetchedUpdatesFromVDR",
    "didDocumentResolvedLocally",
    "didDocumentMetadataResolvedLocally",
)

logger = logging.getLogger("interop.resolution_scenarios")

os.environ.setdefault("DID_WEBPLUS_HTTP_SCHEME_OVERRIDE", HTTP_SCHEME_OVERRIDE)


@dataclass(frozen=True)
class ScenarioMeta:
    """Catalog entry plus fetched resolution-scenario.json."""

    name: str
    path: str
    did: str
    steps: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class StepResult:
    """One step assertion outcome within a scenario."""

    step_index: int
    ok: bool
    detail: str


@dataclass(frozen=True)
class ScenarioRunResult:
    """One (scenario, resolver) run across all steps."""

    name: str
    resolver: str
    ok: bool
    detail: str
    status: CaseStatus
    steps_expected: int
    steps_executed: int
    failed_step_o: int | None
    step_v: tuple[StepResult, ...]


def _server_base_from_catalog(catalog_url: str) -> str:
    """Origin URL for control API (paths at server root, not under catalog)."""
    parsed = urlparse(catalog_url)
    return f"{parsed.scheme}://{parsed.netloc}"


_CONTROL_HTTP_ATTEMPTS = 8
_CONTROL_HTTP_RETRY_DELAY_SECONDS = 0.5


def _is_transient_control_error(exc: BaseException) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in (502, 503, 504)
    if isinstance(exc, urllib.error.URLError):
        return True
    if isinstance(exc, RuntimeError):
        msg = str(exc)
        if "Connection refused" in msg or "Remote end closed connection" in msg:
            return True
        for code in (502, 503, 504):
            if f"HTTP {code}" in msg:
                return True
    return False


_T = TypeVar("_T")


def _with_control_retries(operation: str, fn: Callable[[], _T]) -> _T:
    last_error: BaseException | None = None
    for attempt in range(1, _CONTROL_HTTP_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as exc:
            last_error = exc
            if not _is_transient_control_error(exc) or attempt >= _CONTROL_HTTP_ATTEMPTS:
                raise
            logging.getLogger("interop.resolution_scenarios").warning(
                "%s transient failure (attempt %s/%s): %s",
                operation,
                attempt,
                _CONTROL_HTTP_ATTEMPTS,
                exc,
            )
            time.sleep(_CONTROL_HTTP_RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def _http_post_no_body(url: str, timeout: float, *, expect_status: int) -> None:
    req = urllib.request.Request(url, method="POST", data=b"")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != expect_status:
                raise RuntimeError(
                    f"POST {url}: expected HTTP {expect_status}, got {resp.status}"
                )
    except urllib.error.HTTPError as e:
        if e.code == expect_status:
            return
        raise RuntimeError(f"POST {url} failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"POST {url} failed: {e.reason}") from e


def _http_put_json(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"PUT {url} failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"PUT {url} failed: {e.reason}") from e
    try:
        out = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"PUT {url}: invalid JSON: {e}") from e
    if not isinstance(out, dict):
        raise RuntimeError(f"PUT {url}: response is not a JSON object")
    return out


def _control_reset(server_base: str, timeout: float) -> None:
    url = f"{server_base.rstrip('/')}/control/reset"

    def _call() -> None:
        _http_post_no_body(url, timeout, expect_status=204)

    _with_control_retries(f"POST {url}", _call)


def _control_set_serve_count(
    server_base: str,
    path: str,
    served_did_document_count: int,
    timeout: float,
) -> None:
    url = f"{server_base.rstrip('/')}/control/serve-count"

    def _call() -> None:
        _http_put_json(
            url,
            {"path": path, "servedDidDocumentCount": served_did_document_count},
            timeout,
        )

    _with_control_retries(f"PUT {url}", _call)


def _control_request_count(server_base: str, path: str, timeout: float) -> int:
    qs = urlencode({"path": path})
    url = f"{server_base.rstrip('/')}/control/request-count?{qs}"

    def _call() -> int:
        data = _http_get_json(url, timeout)
        count = data.get("requestCount")
        if not isinstance(count, int):
            raise RuntimeError(f"request-count for {path!r}: missing requestCount int")
        return count

    return _with_control_retries(f"GET {url}", _call)


def _select_scenario_names(
    index: dict[str, Any],
    group_filter_v: list[str],
    name_filter_v: list[str],
) -> list[str]:
    """Default to resolution-scenario group when no filters are given."""
    if not group_filter_v and not name_filter_v:
        group_filter_v = [RESOLUTION_SCENARIO_GROUP]
    return _select_vector_names(index, group_filter_v, name_filter_v)


def _fetch_scenario_meta(
    catalog_url: str,
    name: str,
    index_entry: dict[str, Any],
    timeout: float,
) -> ScenarioMeta:
    path = index_entry.get("path")
    index_did = index_entry.get("did")
    if not isinstance(path, str) or not path:
        raise RuntimeError(f"scenario {name!r}: index entry missing path")
    if not isinstance(index_did, str) or not index_did:
        raise RuntimeError(f"scenario {name!r}: index entry missing did")

    url = _catalog_join(catalog_url, path, "resolution-scenario.json")
    data = _http_get_json(url, timeout)
    fmt = data.get("format")
    if fmt != SCENARIO_FORMAT:
        raise RuntimeError(
            f"scenario {name!r}: format {fmt!r} != expected {SCENARIO_FORMAT!r}"
        )
    did = data.get("did")
    if did != index_did:
        raise RuntimeError(
            f"scenario {name!r}: did mismatch index={index_did!r} scenario={did!r}"
        )
    scenario_name = data.get("name")
    if scenario_name is not None and scenario_name != name:
        raise RuntimeError(
            f"scenario {name!r}: name field {scenario_name!r} != index key"
        )

    steps_raw = data.get("steps")
    if not isinstance(steps_raw, list) or not steps_raw:
        raise RuntimeError(f"scenario {name!r}: steps must be a non-empty list")

    step_v: list[dict[str, Any]] = []
    for i, step in enumerate(steps_raw):
        if not isinstance(step, dict):
            raise RuntimeError(f"scenario {name!r} step {i}: must be object")
        for key in (
            "servedDidDocumentCount",
            "didQuery",
            "resolutionOptions",
            "expected",
        ):
            if key not in step:
                raise RuntimeError(
                    f"scenario {name!r} step {i}: missing {key!r}"
                )
        if not isinstance(step["servedDidDocumentCount"], int):
            raise RuntimeError(
                f"scenario {name!r} step {i}: servedDidDocumentCount must be int"
            )
        if not isinstance(step["didQuery"], str):
            raise RuntimeError(f"scenario {name!r} step {i}: didQuery must be str")
        if not isinstance(step["resolutionOptions"], dict):
            raise RuntimeError(
                f"scenario {name!r} step {i}: resolutionOptions must be object"
            )
        expected = step["expected"]
        if not isinstance(expected, dict):
            raise RuntimeError(f"scenario {name!r} step {i}: expected must be object")
        success = expected.get("success")
        if not isinstance(success, bool):
            raise RuntimeError(
                f"scenario {name!r} step {i}: expected.success must be bool"
            )
        vdr_count = expected.get("vdrRequestCount")
        if not isinstance(vdr_count, int):
            raise RuntimeError(
                f"scenario {name!r} step {i}: expected.vdrRequestCount must be int"
            )
        step_v.append(step)

    return ScenarioMeta(
        name=name,
        path=path,
        did=did,
        steps=tuple(step_v),
    )


def _log_advisory_resolution_metadata(
    expected_meta: dict[str, Any] | None,
    actual_meta: dict[str, Any],
) -> None:
    if not expected_meta:
        return
    if "contentType" in expected_meta:
        exp_ct = expected_meta["contentType"]
        act_ct = actual_meta.get("contentType")
        if act_ct != exp_ct:
            logger.info(
                "advisory contentType: expected %r, got %r", exp_ct, act_ct
            )
    if "error" in expected_meta:
        exp_err = expected_meta["error"]
        act_err = actual_meta.get("error")
        if act_err != exp_err:
            logger.info("advisory error text: expected %r, got %r", exp_err, act_err)


def _resolution_succeeded(result: ResolveResult) -> bool:
    if result.parse_error:
        return False
    if result.returncode != 0:
        return False
    res_meta = result.did_resolution_metadata or {}
    if res_meta.get("error"):
        return False
    return result.did_document is not None


def _assert_normative_step(
    expected: dict[str, Any],
    result: ResolveResult,
) -> tuple[bool, str]:
    failures: list[str] = []
    if result.unsupported_options:
        failures.append(
            "unsupported options: " + ", ".join(result.unsupported_options)
        )

    exp_success = expected["success"]
    res_meta = result.did_resolution_metadata or {}
    exp_res_meta = expected.get("didResolutionMetadata")
    if isinstance(exp_res_meta, dict):
        _log_advisory_resolution_metadata(exp_res_meta, res_meta)

    actual_success = _resolution_succeeded(result)
    if exp_success != actual_success:
        failures.append(
            f"success: expected {exp_success}, resolution {'succeeded' if actual_success else 'failed'}"
        )

    if not exp_success:
        if not res_meta.get("error"):
            failures.append(
                "expected failure but didResolutionMetadata.error is missing"
            )
        if failures:
            return False, "; ".join(failures)
        return True, "expected failure with error"

    if not actual_success:
        if result.parse_error:
            failures.append(result.parse_error)
        elif result.returncode != 0:
            failures.append("resolve exited non-zero")
        elif not result.did_document:
            failures.append("no didDocument in result")
        return False, "; ".join(failures) or "resolution failed"

    doc = result.did_document
    assert doc is not None
    exp_vid = expected.get("didDocumentVersionId")
    if doc.get("versionId") != exp_vid:
        failures.append(
            f"didDocumentVersionId: expected {exp_vid!r}, got {doc.get('versionId')!r}"
        )
    exp_hash = expected.get("didDocumentSelfHash")
    if doc.get("selfHash") != exp_hash:
        failures.append(
            f"didDocumentSelfHash: expected {exp_hash!r}, got {doc.get('selfHash')!r}"
        )

    exp_doc_meta = expected.get("didDocumentMetadata")
    act_doc_meta = result.did_document_metadata
    if exp_doc_meta != act_doc_meta:
        failures.append(
            "didDocumentMetadata mismatch: "
            f"expected {json.dumps(exp_doc_meta, sort_keys=True)}, "
            f"got {json.dumps(act_doc_meta, sort_keys=True)}"
        )

    if isinstance(exp_res_meta, dict):
        for key in NORMATIVE_RESOLUTION_METADATA_KEYS:
            exp_val = exp_res_meta.get(key)
            act_val = res_meta.get(key)
            if exp_val != act_val:
                failures.append(
                    f"didResolutionMetadata.{key}: expected {exp_val!r}, got {act_val!r}"
                )

    if failures:
        return False, "; ".join(failures)
    return True, "ok"


def _step_failure_status(detail: str) -> CaseStatus:
    if "timed out" in detail:
        return "timeout"
    if detail.startswith("harness error:") or detail.startswith("scenario harness error:"):
        return "error"
    return "fail"


def _finalize_scenario_run(
    meta: ScenarioMeta,
    resolver: ResolverKind,
    step_results: list[StepResult],
) -> ScenarioRunResult:
    steps_expected = len(meta.steps)
    steps_executed = len(step_results)
    scenario_ok = all(s.ok for s in step_results) and steps_executed == steps_expected
    failed_step_o: int | None = None
    detail = "ok"
    status: CaseStatus = "pass"
    if not scenario_ok:
        for step in step_results:
            if not step.ok:
                failed_step_o = step.step_index
                detail = step.detail
                status = _step_failure_status(step.detail)
                break
        else:
            detail = (
                f"incomplete: executed {steps_executed}/{steps_expected} steps"
            )
            status = "fail"
    return ScenarioRunResult(
        name=meta.name,
        resolver=resolver,
        ok=scenario_ok,
        detail=detail,
        status=status,
        steps_expected=steps_expected,
        steps_executed=steps_executed,
        failed_step_o=failed_step_o,
        step_v=tuple(step_results),
    )


def _run_scenario(
    meta: ScenarioMeta,
    resolver: ResolverKind,
    *,
    server_base: str,
    timeout: float,
) -> ScenarioRunResult:
    step_results: list[StepResult] = []
    prefix = f"rs-{resolver[:2]}-{meta.name[:12]}-"
    try:
        with tempfile.TemporaryDirectory(prefix=prefix) as store_dir:
            for step_index, step in enumerate(meta.steps):
                expected = step["expected"]
                try:
                    _control_reset(server_base, timeout)
                    _control_set_serve_count(
                        server_base,
                        meta.path,
                        step["servedDidDocumentCount"],
                        timeout,
                    )
                    options = ResolutionOptions.from_wire(step["resolutionOptions"])
                    result = resolve(
                        resolver,
                        step["didQuery"],
                        options=options,
                        store_dir=store_dir,
                        timeout=timeout,
                    )
                    ok, detail = _assert_normative_step(expected, result)
                    if ok:
                        actual_count = _control_request_count(
                            server_base, meta.path, timeout
                        )
                        exp_count = expected["vdrRequestCount"]
                        if actual_count != exp_count:
                            ok = False
                            detail = (
                                f"vdrRequestCount: expected {exp_count}, "
                                f"got {actual_count}"
                            )
                except subprocess.TimeoutExpired:
                    ok, detail = False, f"resolver timed out after {timeout}s"
                except Exception as e:
                    ok, detail = False, f"harness error: {e}"

                step_results.append(
                    StepResult(step_index=step_index, ok=ok, detail=detail)
                )
                status = "PASS" if ok else "FAIL"
                line = (
                    f"  {status} {resolver} {meta.name} step {step_index}"
                )
                if not ok:
                    line = f"{line}: {detail}"
                print(line, flush=True)
                if not ok:
                    break
    except Exception as e:
        step_results.append(
            StepResult(
                step_index=0,
                ok=False,
                detail=f"scenario harness error: {e}",
            )
        )

    return _finalize_scenario_run(meta, resolver, step_results)


def _case_to_json(case: ScenarioRunResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": case.name,
        "resolver": case.resolver,
        "ok": case.ok,
        "status": case.status,
        "detail": case.detail,
        "steps_expected": case.steps_expected,
        "steps_executed": case.steps_executed,
    }
    if case.failed_step_o is not None:
        payload["failedStep"] = case.failed_step_o
    return payload


def _write_suite_artifact(
    path: Path,
    *,
    config: dict[str, Any],
    cases: list[ScenarioRunResult],
    expected: int,
    executed: int,
    expected_by_resolver_m: dict[str, int],
    duration_seconds: float,
    runner_exit_code: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "suite": SUITE_ID,
        "kind": "scenarios",
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


def _print_summary(result_v: list[ScenarioRunResult]) -> None:
    by_resolver: dict[str, list[ScenarioRunResult]] = defaultdict(list)
    for r in result_v:
        by_resolver[r.resolver].append(r)

    for resolver in sorted(by_resolver):
        cases = by_resolver[resolver]
        passed = sum(1 for c in cases if c.ok)
        print(f"\n=== {resolver} ===")
        print(f"  {passed}/{len(cases)} scenarios passed")

        fail_v = [c for c in cases if not c.ok]
        print(f"\n  --- Failures ({len(fail_v)}) ---")
        if not fail_v:
            print("    (none)")
        else:
            for c in fail_v:
                for step in c.step_v:
                    if not step.ok:
                        print(
                            f"    FAIL {c.name} step {step.step_index}: "
                            f"{step.detail}"
                        )
                        break
                else:
                    print(f"    FAIL {c.name}: incomplete steps")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run did-webplus resolution-scenario catalog against interop resolvers."
        ),
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
        help=(
            "Include scenarios from this index group (repeatable; "
            f"default: {RESOLUTION_SCENARIO_GROUP} when no filters)"
        ),
    )
    parser.add_argument(
        "--name",
        action="append",
        default=[],
        metavar="NAME",
        help="Include this scenario by name (repeatable)",
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
    result_v: list[ScenarioRunResult] = []
    expected = 0
    executed = 0
    expected_by_resolver_m: dict[str, int] = {}

    try:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s %(name)s: %(message)s",
        )

        resolver_v: list[ResolverKind] = (
            list(RESOLVER_CHOICES) if args.resolver == "all" else [args.resolver]  # type: ignore[list-item]
        )

        server_base = _server_base_from_catalog(args.catalog_url)

        try:
            index = _fetch_index(args.catalog_url, args.timeout)
            name_v = _select_scenario_names(index, args.group, args.name)
            meta_v: list[ScenarioMeta] = []
            for name in name_v:
                meta_v.append(
                    _fetch_scenario_meta(
                        args.catalog_url,
                        name,
                        index["vectors"][name],
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
            f"Running {len(meta_v)} resolution scenario(s) × {len(resolver_v)} resolver(s) "
            f"sequentially, timeout={args.timeout}s"
        )
        print(f"Control API: {server_base}")

        for meta in meta_v:
            for resolver in resolver_v:
                print(f"\n--- {meta.name} / {resolver} ---", flush=True)
                run = _run_scenario(
                    meta,
                    resolver,
                    server_base=server_base,
                    timeout=args.timeout,
                )
                status = "PASS" if run.ok else "FAIL"
                print(f"{status} {resolver} {meta.name}", flush=True)
                result_v.append(run)

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
