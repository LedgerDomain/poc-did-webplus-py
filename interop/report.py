#!/usr/bin/env python3
"""Aggregate interop run artifacts into report.json and report.md (host-side)."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

INTEROP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(INTEROP_DIR))

from resolvers import PYTHON_CLI_IMAGE, RUST_CLI_IMAGE, ZKRED_IMAGE  # noqa: E402

REPORT_SCHEMA_VERSION = 1

DEFAULT_CATALOG_RESOLVERS = ("python", "rust", "zkred")

ENV_REPRO_KEYS = (
    "INTEROP_ZKRED_DID_WEBPLUS_VERSION",
    "TEST_VECTOR_HEALTH_TIMEOUT_SECONDS",
    "DID_WEBPLUS_INTEROP_DOCKER_NETWORK",
    "INTEROP_ZKRED_LOCAL",
    "RUST_VDR_VDG_HOSTS",
    "PYTHON_VDR_VDG_HOSTS",
)

COMPOSE_PATH = INTEROP_DIR / "docker-compose.yml"
PACKAGE_LOCK_PATH = INTEROP_DIR / "package-lock.json"

RUST_VDR_IMAGE = "ghcr.io/ledgerdomain/did-webplus-vdr:v0.1.4"
RUST_VDG_IMAGE = "ghcr.io/ledgerdomain/did-webplus-vdg:v0.1.4"

COMPOSE_IMAGE_LINE_RE = re.compile(r"^\s+image:\s+(\S+)\s*$", re.MULTILINE)

TEST_VECTOR_CATALOG_PATH = "ledgerdomain.github.io/did-webplus-spec/test-vector"
TEST_VECTOR_SERVER_DISPLAY = (
    "Built for interop testing; serves the test-vector catalog at "
    f"{TEST_VECTOR_CATALOG_PATH}"
)

Verdict = Literal["PASS", "FAIL"]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected JSON object")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _matrix_suite_id(scenario: int) -> str:
    return f"matrix-{scenario:02d}"


def _resolve_full_git_sha(sha: str) -> str:
    if len(sha) >= 40:
        return sha
    repo_root = INTEROP_DIR.parent
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", sha],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return sha
    if proc.returncode == 0:
        full = proc.stdout.strip()
        if full:
            return full
    return sha


def _pinned_zkred_version() -> str:
    try:
        lock = json.loads(PACKAGE_LOCK_PATH.read_text(encoding="utf-8"))
        return str(
            lock["packages"]["node_modules/@zkred/did-webplus"]["version"]
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return "unknown"


def _parse_compose_image_tags() -> list[str]:
    try:
        text = COMPOSE_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    return list(dict.fromkeys(COMPOSE_IMAGE_LINE_RE.findall(text)))


def _docker_image_inspect(image_ref: str) -> dict[str, Any]:
    """Return image id and repo digests for a local tag or name."""
    fmt = "{{.Id}} {{range .RepoDigests}}{{.}} {{end}}"
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", "--format", fmt, image_ref],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ref": image_ref, "id": None, "repoDigests": [], "error": str(exc)}
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return {"ref": image_ref, "id": None, "repoDigests": [], "error": err}
    parts = proc.stdout.strip().split()
    if not parts:
        return {"ref": image_ref, "id": None, "repoDigests": [], "error": "empty inspect"}
    image_id = parts[0]
    digests = [p for p in parts[1:] if p.startswith("ghcr.io/") or "@" in p]
    return {"ref": image_ref, "id": image_id, "repoDigests": digests, "error": None}


def _compose_service_images() -> dict[str, str]:
    """Map compose service name -> local image ref (pinned tag or compose-built name)."""
    try:
        proc = subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_PATH), "config", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(INTEROP_DIR),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        config = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}
    if not isinstance(config, dict):
        return {}
    project = str(config.get("name") or INTEROP_DIR.name)
    services = config.get("services")
    if not isinstance(services, dict):
        return {}
    images_m: dict[str, str] = {}
    for service_name, svc in services.items():
        if not isinstance(svc, dict):
            continue
        image = svc.get("image")
        if image:
            images_m[str(service_name)] = str(image)
        elif svc.get("build"):
            images_m[str(service_name)] = f"{project}-{service_name}"
    return images_m


def _env_repro_prefix(env_m: dict[str, Any]) -> str:
    parts_v: list[str] = []
    for key in ENV_REPRO_KEYS:
        val = env_m.get(key)
        if val is None or val == "":
            continue
        parts_v.append(f"{key}={_shell_quote(str(val))}")
    if not parts_v:
        return ""
    return " ".join(parts_v) + " "


def _shell_quote(s: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@+-]+", s):
        return s
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _repro_run_sh(
    env_m: dict[str, Any],
    invocation_tail_v: list[str],
) -> str:
    prefix = _env_repro_prefix(env_m)
    return f"{prefix}./run.sh {' '.join(invocation_tail_v)}"


def _case_is_complete(case: dict[str, Any], kind: str) -> bool:
    status = str(case.get("status", "pass" if case.get("ok") else "fail")).lower()
    if status in ("error", "timeout", "not-run"):
        return False
    if kind == "scenarios":
        steps_expected = case.get("steps_expected")
        steps_executed = case.get("steps_executed")
        if steps_expected is not None and steps_executed is not None:
            if int(steps_executed) < int(steps_expected):
                return False
    return True


def _case_counts_as_passed(case: dict[str, Any], kind: str) -> bool:
    if not case.get("ok"):
        return False
    if not _case_is_complete(case, kind):
        return False
    status = str(case.get("status", "pass")).lower()
    return status == "pass"


def _catalog_resolvers_for_planned(
    planned: dict[str, Any],
    suite_data: dict[str, Any] | None,
) -> list[str]:
    if planned.get("resolvers"):
        return [str(r) for r in planned["resolvers"]]
    if suite_data:
        config = suite_data.get("config") or {}
        resolver = config.get("resolver")
        if resolver and resolver != "all":
            return [str(resolver)]
        case_v = suite_data.get("cases") or []
        from_cases = sorted({str(c.get("resolver")) for c in case_v if c.get("resolver")})
        if from_cases:
            return from_cases
    return list(DEFAULT_CATALOG_RESOLVERS)


def _format_component_inventory_line(key: str, comp: dict[str, Any]) -> str:
    label = comp.get("displayLabel") or comp.get("imageRef") or "—"
    image_id = comp.get("imageId")
    if image_id:
        id_part = f"image ID `{image_id}`"
    elif comp.get("imageInspectError"):
        id_part = f"image ID unavailable ({comp['imageInspectError']})"
    else:
        id_part = "image ID unavailable"
    meta_v: list[str] = []
    if comp.get("builtFromThisRepo") and not comp.get("displayLabel"):
        meta_v.append("from this repo")
    if comp.get("zkredPackageVersion"):
        meta_v.append(f"zkred pin `{comp['zkredPackageVersion']}`")
    if comp.get("catalogSubmoduleSha"):
        meta_v.append(f"catalog submodule `{comp['catalogSubmoduleSha']}`")
    meta_s = f" ({', '.join(meta_v)})" if meta_v else ""
    return f"- **{key}:** {label} — {id_part}{meta_s}"


def _component_inventory(
    run_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    git = run_data.get("git") or {}
    catalog_sha = git.get("catalogSubmoduleSha")
    zkred_pin = run_data.get("zkredPin") or _pinned_zkred_version()

    service_images_m = _compose_service_images()
    python_vdr_ref = service_images_m.get("python-vdr")
    tvs_ref = service_images_m.get("ledgerdomain.github.io")

    compose_tags = set(_parse_compose_image_tags())
    compose_tags.update(
        {RUST_VDR_IMAGE, RUST_VDG_IMAGE, RUST_CLI_IMAGE, PYTHON_CLI_IMAGE, ZKRED_IMAGE}
    )
    if python_vdr_ref:
        compose_tags.add(python_vdr_ref)
    if tvs_ref:
        compose_tags.add(tvs_ref)

    inspect_m: dict[str, dict[str, Any]] = {}
    for ref in sorted(compose_tags):
        inspect_m[ref] = _docker_image_inspect(ref)

    def _entry(
        *,
        role: str,
        image_ref: str | None,
        built_from_this_repo: bool = False,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": role}
        if built_from_this_repo:
            payload["builtFromThisRepo"] = True
        if image_ref:
            payload["imageRef"] = image_ref
            insp = inspect_m.get(image_ref) or _docker_image_inspect(image_ref)
            if insp.get("id"):
                payload["imageId"] = insp["id"]
            if insp.get("repoDigests"):
                payload["repoDigests"] = insp["repoDigests"]
            if insp.get("error"):
                payload["imageInspectError"] = insp["error"]
        if extra:
            payload.update(extra)
        return payload

    rust_cli_insp = inspect_m.get(RUST_CLI_IMAGE) or _docker_image_inspect(RUST_CLI_IMAGE)

    inventory: dict[str, dict[str, Any]] = {
        "controller/python": _entry(
            role="controller",
            image_ref=PYTHON_CLI_IMAGE,
            built_from_this_repo=True,
            extra={"implementation": "python"},
        ),
        "resolver/python": _entry(
            role="resolver",
            image_ref=PYTHON_CLI_IMAGE,
            built_from_this_repo=True,
            extra={"implementation": "python"},
        ),
        "vdr/python": _entry(
            role="vdr",
            image_ref=python_vdr_ref,
            built_from_this_repo=True,
            extra={"implementation": "python", "listenPort": 8087},
        ),
        "controller/rust": _entry(
            role="controller",
            image_ref=RUST_CLI_IMAGE,
            extra={
                "implementation": "rust",
                "repoDigests": rust_cli_insp.get("repoDigests") or [],
            },
        ),
        "resolver/rust": _entry(
            role="resolver",
            image_ref=RUST_CLI_IMAGE,
            extra={
                "implementation": "rust",
                "repoDigests": rust_cli_insp.get("repoDigests") or [],
            },
        ),
        "vdr/rust": _entry(
            role="vdr",
            image_ref=RUST_VDR_IMAGE,
            extra={"implementation": "rust", "listenPort": 8085},
        ),
        "vdg/rust": _entry(
            role="vdg",
            image_ref=RUST_VDG_IMAGE,
            extra={"implementation": "rust", "listenPort": 8086},
        ),
        "controller/zkred": _entry(
            role="controller",
            image_ref=ZKRED_IMAGE,
            built_from_this_repo=True,
            extra={
                "implementation": "zkred",
                "zkredPackageVersion": zkred_pin,
            },
        ),
        "resolver/zkred": _entry(
            role="resolver",
            image_ref=ZKRED_IMAGE,
            built_from_this_repo=True,
            extra={
                "implementation": "zkred",
                "zkredPackageVersion": zkred_pin,
            },
        ),
        "vdr/test-vector-server": _entry(
            role="vdr",
            image_ref=tvs_ref,
            built_from_this_repo=True,
            extra={
                "implementation": "test-vector-server",
                "displayLabel": TEST_VECTOR_SERVER_DISPLAY,
                "catalogUrl": TEST_VECTOR_CATALOG_PATH,
                "listenPort": 80,
                "catalogSubmoduleSha": catalog_sha,
                "source": "interop/test_vector_server.py",
            },
        ),
    }
    return inventory


def _matrix_axes_from_scenario(scenario: int) -> dict[str, Any]:
    """Scenario axis mapping (mirrors interop/run_interop_tests.py)."""
    if 17 <= scenario <= 22:
        mapping: dict[int, tuple[str, str, str, bool]] = {
            17: ("python", "python", "zkred", False),
            18: ("python", "python", "zkred", True),
            19: ("rust", "rust", "zkred", False),
            20: ("rust", "rust", "zkred", True),
            21: ("zkred", "python", "both", False),
            22: ("zkred", "rust", "both", False),
        }
        controller, vdr, resolver, use_vdg = mapping[scenario]
    else:
        n0 = scenario - 1
        controller = "rust" if (n0 & 8) else "python"
        vdr = "rust" if (n0 & 4) else "python"
        resolver = "rust" if (n0 & 2) else "python"
        use_vdg = bool(n0 & 1)
    return {
        "controller": controller,
        "vdr": vdr,
        "resolver": resolver,
        "vdg": use_vdg,
    }


def _matrix_axes_from_suite(suite_data: dict[str, Any] | None, scenario: int) -> dict[str, Any]:
    if suite_data:
        cases = suite_data.get("cases") or []
        if cases:
            axes = cases[0].get("axes")
            if isinstance(axes, dict) and axes:
                return dict(axes)
    return _matrix_axes_from_scenario(scenario)


RoleValue = Literal["python", "rust", "zkred", "test-vector-server", "none"]

_CATALOG_VDR_ROLE: RoleValue = "test-vector-server"


def _matrix_resolver_role(resolver: Any) -> str:
    if resolver == "both":
        return "python, rust"
    if resolver in ("python", "rust", "zkred"):
        return str(resolver)
    return "none"


def _matrix_vdg_role(use_vdg: Any) -> RoleValue:
    return "rust" if use_vdg else "none"


def _roles_from_matrix_axes(axes: dict[str, Any]) -> dict[str, str]:
    controller = axes.get("controller")
    vdr = axes.get("vdr")
    return {
        "controller": controller if controller in ("python", "rust", "zkred") else "none",
        "vdr": vdr if vdr in ("python", "rust") else "none",
        "vdg": _matrix_vdg_role(axes.get("vdg")),
        "resolver": _matrix_resolver_role(axes.get("resolver")),
    }


def _roles_from_catalog(resolver: str) -> dict[str, str]:
    resolver_role = resolver if resolver in ("python", "rust", "zkred") else "none"
    return {
        "controller": "none",
        "vdr": _CATALOG_VDR_ROLE,
        "vdg": "none",
        "resolver": resolver_role,
    }


def _matrix_component_keys(axes: dict[str, Any] | None) -> list[str]:
    if not axes:
        return []
    keys_v: list[str] = []
    controller = axes.get("controller")
    vdr = axes.get("vdr")
    resolver = axes.get("resolver")
    if controller in ("python", "rust", "zkred"):
        keys_v.append(f"controller/{controller}")
    if vdr in ("python", "rust"):
        keys_v.append(f"vdr/{vdr}")
    if resolver in ("python", "rust", "zkred"):
        keys_v.append(f"resolver/{resolver}")
    elif resolver == "both":
        keys_v.extend(["resolver/python", "resolver/rust"])
    if axes.get("vdg"):
        keys_v.append("vdg/rust")
    return keys_v


def _catalog_component_keys(resolver: str) -> list[str]:
    keys_v = ["vdr/test-vector-server"]
    if resolver in ("python", "rust", "zkred"):
        keys_v.append(f"resolver/{resolver}")
    return keys_v


def _collect_invoked_component_keys(units_v: list[dict[str, Any]]) -> set[str]:
    keys_s: set[str] = set()
    for unit in units_v:
        if unit.get("notRun"):
            continue
        kind = unit.get("kind")
        if kind == "matrix":
            for key in unit.get("componentKeys") or []:
                keys_s.add(str(key))
        elif kind in ("vectors", "scenarios"):
            keys_s.update(_catalog_component_keys(str(unit.get("resolver") or "")))
    return keys_s


def _enrich_unit_roles(units_v: list[dict[str, Any]]) -> None:
    for unit in units_v:
        kind = unit.get("kind")
        if kind == "matrix":
            axes = unit.get("axes")
            if not isinstance(axes, dict) or not axes:
                scenario = int(unit.get("scenario") or 0)
                axes = _matrix_axes_from_scenario(scenario)
                unit["axes"] = axes
            keys_v = unit.get("componentKeys")
            if not keys_v:
                unit["componentKeys"] = _matrix_component_keys(axes)
            unit["roles"] = _roles_from_matrix_axes(axes)
        elif kind in ("vectors", "scenarios"):
            unit["roles"] = _roles_from_catalog(str(unit.get("resolver") or "none"))


def _unit_role(unit: dict[str, Any], role: str) -> str:
    roles = unit.get("roles") or {}
    value = roles.get(role)
    return str(value) if value is not None else "none"


def _catalog_case_repro(
    env_m: dict[str, Any],
    suite_kind: str,
    resolver: str,
    case_name: str,
    config: dict[str, Any],
) -> str:
    tail_v = [suite_kind, "--resolver", resolver, "--name", case_name]
    flag_key_m = {
        "group": "--group",
        "catalog_url": "--catalog-url",
        "timeout": "--timeout",
        "jobs": "--jobs",
    }
    for key, flag in flag_key_m.items():
        if key not in config:
            continue
        raw = config[key]
        if raw in (None, "", []):
            continue
        if isinstance(raw, list):
            for item in raw:
                tail_v.extend([flag, str(item)])
        else:
            tail_v.extend([flag, str(raw)])
    return _repro_run_sh(env_m, tail_v)


def _resolver_expected_count(
    suite_data: dict[str, Any],
    resolver: str,
    resolvers_v: list[str],
    case_v: list[dict[str, Any]],
) -> int:
    by_resolver = suite_data.get("expectedByResolver")
    if isinstance(by_resolver, dict) and resolver in by_resolver:
        return int(by_resolver[resolver])
    total_expected = int(suite_data.get("expected") or 0)
    n_resolvers = len(resolvers_v) or 1
    if total_expected and n_resolvers:
        return total_expected // n_resolvers
    return len(case_v)


def _build_units_and_failures(
    run_data: dict[str, Any],
    suite_m: dict[str, dict[str, Any]],
    env_m: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    planned_v = run_data.get("plannedUnits") or []
    units_v: list[dict[str, Any]] = []
    failures_v: list[dict[str, Any]] = []

    for planned in planned_v:
        kind = planned.get("kind")
        if kind == "matrix":
            scenario = int(planned["scenario"])
            suite_id = planned.get("suite") or _matrix_suite_id(scenario)
            log_rel = f"logs/{suite_id}.log"
            suite_rel = f"suites/{suite_id}.json"
            suite_data = suite_m.get(suite_id)
            unit_id = f"matrix:{scenario}"
            repro = _repro_run_sh(env_m, ["matrix", str(scenario)])

            if suite_data is None:
                axes = _matrix_axes_from_scenario(scenario)
                units_v.append(
                    {
                        "id": unit_id,
                        "kind": "matrix",
                        "scenario": scenario,
                        "axes": axes,
                        "componentKeys": _matrix_component_keys(axes),
                        "verdict": "FAIL",
                        "passed": 0,
                        "expected": 1,
                        "durationSeconds": None,
                        "repro": repro,
                        "log": log_rel,
                        "suiteArtifact": suite_rel,
                        "notRun": True,
                    }
                )
                failures_v.append(
                    {
                        "unitId": unit_id,
                        "caseName": suite_id,
                        "detail": "Suite artifact missing (runner did not finish)",
                        "failedStep": None,
                        "caseRepro": repro,
                    }
                )
                continue

            cases = suite_data.get("cases") or []
            kind_suite = str(suite_data.get("kind") or "matrix")
            expected = int(suite_data.get("expected") or max(1, len(cases)))
            passed = sum(1 for c in cases if _case_counts_as_passed(c, kind_suite))
            duration = suite_data.get("durationSeconds")
            if not cases:
                verdict: Verdict = (
                    "PASS" if suite_data.get("runnerExitCode") == 0 else "FAIL"
                )
                passed = 1 if verdict == "PASS" else 0
            else:
                verdict = (
                    "PASS"
                    if passed == expected
                    and len(cases) >= expected
                    and all(_case_counts_as_passed(c, kind_suite) for c in cases)
                    else "FAIL"
                )

            axes = _matrix_axes_from_suite(suite_data, scenario)
            units_v.append(
                {
                    "id": unit_id,
                    "kind": "matrix",
                    "scenario": scenario,
                    "axes": axes,
                    "verdict": verdict,
                    "passed": passed,
                    "expected": expected,
                    "durationSeconds": duration,
                    "repro": repro,
                    "log": log_rel,
                    "suiteArtifact": suite_rel,
                    "componentKeys": _matrix_component_keys(axes),
                    "notRun": False,
                }
            )
            for case in cases:
                if _case_counts_as_passed(case, kind_suite):
                    continue
                failures_v.append(
                    {
                        "unitId": unit_id,
                        "caseName": case.get("name") or f"scenario-{scenario}",
                        "detail": case.get("detail") or "failed",
                        "failedStep": case.get("failedStep"),
                        "caseRepro": repro,
                    }
                )
            continue

        if kind in ("vectors", "scenarios"):
            suite_id = planned.get("suite") or kind
            suite_data = suite_m.get(suite_id)
            log_rel = f"logs/{suite_id}.log"
            suite_rel = f"suites/{suite_id}.json"
            resolvers_v = _catalog_resolvers_for_planned(planned, suite_data)
            config = (suite_data or {}).get("config") or {}
            cases_by_resolver: dict[str, list[dict[str, Any]]] = defaultdict(list)
            if suite_data:
                for case in suite_data.get("cases") or []:
                    res = str(case.get("resolver", ""))
                    if res:
                        cases_by_resolver[res].append(case)

            for resolver in resolvers_v:
                unit_id = f"{kind}:{resolver}"
                repro = _repro_run_sh(env_m, [kind, "--resolver", resolver])
                if suite_data is None:
                    units_v.append(
                        {
                            "id": unit_id,
                            "kind": kind,
                            "resolver": resolver,
                            "verdict": "FAIL",
                            "passed": 0,
                            "expected": 0,
                            "durationSeconds": None,
                            "repro": repro,
                            "log": log_rel,
                            "suiteArtifact": suite_rel,
                            "notRun": True,
                        }
                    )
                    failures_v.append(
                        {
                            "unitId": unit_id,
                            "caseName": suite_id,
                            "detail": "Suite artifact missing (runner did not finish)",
                            "failedStep": None,
                            "caseRepro": repro,
                        }
                    )
                    continue

                case_v = cases_by_resolver.get(resolver, [])
                kind_suite = str(suite_data.get("kind") or kind)
                passed = sum(1 for c in case_v if _case_counts_as_passed(c, kind_suite))
                expected = _resolver_expected_count(
                    suite_data, resolver, resolvers_v, case_v
                )
                duration = suite_data.get("durationSeconds")
                executed = len(case_v)
                if (
                    expected > 0
                    and passed == expected
                    and executed >= expected
                    and all(_case_counts_as_passed(c, kind_suite) for c in case_v)
                ):
                    verdict = "PASS"
                elif expected == 0 and not case_v and suite_data.get("runnerExitCode") == 0:
                    verdict = "PASS"
                else:
                    verdict = "FAIL"

                units_v.append(
                    {
                        "id": unit_id,
                        "kind": kind,
                        "resolver": resolver,
                        "verdict": verdict,
                        "passed": passed,
                        "expected": expected,
                        "durationSeconds": duration,
                        "repro": repro,
                        "log": log_rel,
                        "suiteArtifact": suite_rel,
                        "notRun": False,
                    }
                )
                for case in case_v:
                    if _case_counts_as_passed(case, kind_suite):
                        continue
                    name = str(case.get("name", ""))
                    failures_v.append(
                        {
                            "unitId": unit_id,
                            "caseName": name,
                            "detail": case.get("detail") or "failed",
                            "failedStep": case.get("failedStep"),
                            "caseRepro": _catalog_case_repro(
                                env_m, kind, resolver, name, config
                            ),
                        }
                    )
            continue

    return units_v, failures_v


def _load_suite_artifacts(suites_dir: Path) -> dict[str, dict[str, Any]]:
    suite_m: dict[str, dict[str, Any]] = {}
    if not suites_dir.is_dir():
        return suite_m
    for path in sorted(suites_dir.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        suite_id = str(data.get("suite") or path.stem)
        suite_m[suite_id] = data
    return suite_m


def build_report(report_dir: Path) -> dict[str, Any]:
    run_path = report_dir / "run.json"
    if not run_path.is_file():
        raise FileNotFoundError(f"Missing run.json in {report_dir}")

    run_data = _read_json(run_path)
    suite_m = _load_suite_artifacts(report_dir / "suites")
    env_m = run_data.get("env") or {}
    if not isinstance(env_m, dict):
        env_m = {}

    full_components_m = _component_inventory(run_data)
    units_v, failures_v = _build_units_and_failures(run_data, suite_m, env_m)
    _enrich_unit_roles(units_v)
    invoked_keys_s = _collect_invoked_component_keys(units_v)
    components = {
        key: full_components_m[key]
        for key in sorted(invoked_keys_s)
        if key in full_components_m
    }

    git_m = dict(run_data.get("git") or {})
    sha = git_m.get("sha")
    if isinstance(sha, str) and sha and sha != "unknown":
        git_m["sha"] = _resolve_full_git_sha(sha)

    started_at = run_data.get("startedAt")
    ended_at = run_data.get("endedAt") or _utc_now_iso()
    duration_seconds = None
    if started_at and ended_at:
        try:
            start_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(str(ended_at).replace("Z", "+00:00"))
            duration_seconds = max(0.0, (end_dt - start_dt).total_seconds())
        except ValueError:
            duration_seconds = None

    report: dict[str, Any] = {
        "schemaVersion": REPORT_SCHEMA_VERSION,
        "generatedAt": _utc_now_iso(),
        "runId": run_data.get("runId"),
        "invocation": run_data.get("invocation"),
        "argv": run_data.get("argv"),
        "startedAt": started_at,
        "endedAt": ended_at,
        "durationSeconds": duration_seconds,
        "env": env_m,
        "host": run_data.get("host"),
        "git": git_m,
        "zkredPin": run_data.get("zkredPin"),
        "components": components,
        "units": units_v,
        "failures": failures_v,
        "logsDir": "logs",
        "suitesDir": "suites",
    }
    return report


def render_report_md(report: dict[str, Any], report_dir: Path) -> str:
    lines: list[str] = []
    git = report.get("git") or {}
    host = report.get("host") or {}
    dirty = git.get("dirty")
    dirty_s = " (dirty)" if dirty else ""

    lines.append("# Interop run report")
    lines.append("")
    lines.append("## Header")
    lines.append("")
    lines.append(f"- **Run ID:** `{report.get('runId')}`")
    lines.append(f"- **Generated:** {report.get('generatedAt')}")
    if report.get("startedAt"):
        lines.append(f"- **Started:** {report.get('startedAt')}")
    if report.get("endedAt"):
        lines.append(f"- **Ended:** {report.get('endedAt')}")
    if report.get("durationSeconds") is not None:
        lines.append(f"- **Duration:** {report['durationSeconds']:.1f}s")
    argv_v = report.get("argv") or []
    if argv_v:
        lines.append(f"- **Invocation:** `{' '.join(str(a) for a in argv_v)}`")
    lines.append(
        f"- **Test repo git commit hash:** `{git.get('sha', '?')}` "
        f"on `{git.get('branch', '?')}`{dirty_s}"
    )
    if git.get("catalogSubmoduleSha"):
        lines.append(f"- **Catalog submodule:** `{git.get('catalogSubmoduleSha')}`")
    if host:
        machine = host.get("machine") or host.get("arch")
        kernel = host.get("kernel")
        lines.append(
            f"- **Host:** {machine or '?'} / {kernel or '?'}; "
            f"cpus={host.get('cpuCount', '?')}; "
            f"docker={host.get('dockerVersion', '?')}; "
            f"compose={host.get('composeVersion', '?')}"
        )
    lines.append("")

    lines.append("## Verdicts")
    lines.append("")
    lines.append(
        "| Unit | Controller | VDR | VDG | Resolver | Verdict | Passed | Expected | "
        "Duration | Repro |"
    )
    lines.append(
        "|------|------------|-----|-----|----------|---------|--------|----------|"
        "----------|-------|"
    )
    for unit in report.get("units") or []:
        uid = unit.get("id", "")
        verdict = unit.get("verdict", "")
        passed = unit.get("passed", "")
        expected = unit.get("expected", "")
        dur = unit.get("durationSeconds")
        dur_s = f"{dur:.1f}s" if isinstance(dur, (int, float)) else "—"
        repro = unit.get("repro", "")
        if unit.get("notRun"):
            verdict = "FAIL (not-run)"
        ctrl = _unit_role(unit, "controller")
        vdr = _unit_role(unit, "vdr")
        vdg = _unit_role(unit, "vdg")
        resolver = _unit_role(unit, "resolver")
        lines.append(
            f"| `{uid}` | {ctrl} | {vdr} | {vdg} | {resolver} | {verdict} | {passed} | "
            f"{expected} | {dur_s} | `{repro}` |"
        )
    lines.append("")

    lines.append("## Invoked components")
    lines.append("")
    components_m = report.get("components") or {}
    if not components_m:
        lines.append("_None (no units ran)._")
    else:
        for key, comp in sorted(components_m.items()):
            lines.append(_format_component_inventory_line(key, comp))
    lines.append("")

    failures_v = report.get("failures") or []
    lines.append("## Failures")
    lines.append("")
    if not failures_v:
        lines.append("_None._")
    else:
        for fail in failures_v:
            lines.append(f"### `{fail.get('unitId')}` — {fail.get('caseName')}")
            lines.append("")
            unit = next(
                (u for u in (report.get("units") or []) if u.get("id") == fail.get("unitId")),
                None,
            )
            if unit and unit.get("roles"):
                roles = unit["roles"]
                lines.append(
                    "- **Roles:** "
                    f"controller={roles.get('controller')}, vdr={roles.get('vdr')}, "
                    f"vdg={roles.get('vdg')}, resolver={roles.get('resolver')}"
                )
            if fail.get("failedStep"):
                lines.append(f"- **Step:** {fail.get('failedStep')}")
            lines.append(f"- **Detail:** {fail.get('detail')}")
            lines.append(f"- **Case repro:** `{fail.get('caseRepro')}`")
            if unit and unit.get("log"):
                log_path = report_dir / str(unit["log"])
                lines.append(
                    f"- **Suite log:** `{unit['log']}` "
                    f"(docker run reproducers are in the tee'd log)"
                )
                if not log_path.is_file():
                    lines.append("  - _Log file not found on disk._")
            lines.append("")

    lines.append("## Logs")
    lines.append("")
    logs_dir = report_dir / "logs"
    if logs_dir.is_dir():
        for path in sorted(logs_dir.glob("*.log")):
            rel = f"logs/{path.name}"
            lines.append(f"- `{rel}`")
    else:
        lines.append("_No logs directory._")
    lines.append("")
    return "\n".join(lines)


def write_reports(report_dir: Path) -> dict[str, Any]:
    report = build_report(report_dir)
    _write_json(report_dir / "report.json", report)
    md = render_report_md(report, report_dir)
    (report_dir / "report.md").write_text(md, encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build interop report.json and report.md")
    parser.add_argument(
        "report_dir",
        type=Path,
        help="Report run directory containing run.json and suites/",
    )
    args = parser.parse_args(argv)
    report_dir = args.report_dir.resolve()
    try:
        write_reports(report_dir)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {report_dir / 'report.json'} and {report_dir / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
