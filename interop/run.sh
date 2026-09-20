#!/usr/bin/env bash
# Unified entry point for did:webplus interop suites.
#
#   ./run.sh matrix [1-22]     22-scenario controller/VDR/resolver matrix (all if omitted)
#   ./run.sh vectors [args…]   test-vector catalog (forwards to run_test_vectors.py)
#   ./run.sh scenarios [args…] resolution-scenario catalog (forwards to run_resolution_scenarios.py)
#   ./run.sh all               matrix (all) + vectors + scenarios
#   ./run.sh clean             stop containers, remove volumes, reset wallets/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RUN_SH_ORIGINAL_ARGV=("$0" "$@")
RUN_SH_ORIGINAL_ARGV_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$0" "$@")"

SERVICE="ledgerdomain.github.io"
HEALTH_TIMEOUT_SECONDS="${TEST_VECTOR_HEALTH_TIMEOUT_SECONDS:-60}"
CATALOG_INDEX="ledgerdomain.github.io/did-webplus-spec/test-vector/index.json"

usage() {
    cat <<'EOF'
Usage:
  ./run.sh matrix [1-22]       Run one matrix scenario, or all 22 if omitted
  ./run.sh vectors [filters…]  Test-vector resolver conformance (see resolver-conformance-testing.md)
  ./run.sh scenarios [filters…] Resolution-scenario conformance (sequential control API)
  ./run.sh all                 matrix (all) + vectors + scenarios
  ./run.sh clean               docker compose down -v and reset interop wallets

Matrix filters: scenario number 1–22 only.
Vector/scenario filters: --resolver, --name, --group (vectors), etc. — passed through to the Python runner.

Optional env: INTEROP_ZKRED_DID_WEBPLUS_VERSION, TEST_VECTOR_HEALTH_TIMEOUT_SECONDS
EOF
}

detect_compose() {
    if command -v docker &>/dev/null; then
        if docker compose version &>/dev/null; then
            COMPOSE="docker compose"
        elif docker-compose version &>/dev/null; then
            COMPOSE="docker-compose"
        else
            echo "Error: docker compose or docker-compose required"
            exit 1
        fi
    else
        echo "Error: docker required"
        exit 1
    fi
}

pinned_ts_version() {
    python3 -c "import json; print(json.load(open('package-lock.json'))['packages']['node_modules/@zkred/did-webplus']['version'])" 2>/dev/null \
        || echo "unknown"
}

# --- Run report artifacts (interop/reports/<RUN_ID>/); see report.py ---
INTEROP_ENV_WHITELIST=(
    INTEROP_ZKRED_DID_WEBPLUS_VERSION
    TEST_VECTOR_HEALTH_TIMEOUT_SECONDS
    DID_WEBPLUS_INTEROP_DOCKER_NETWORK
    INTEROP_ZKRED_LOCAL
    RUST_VDR_VDG_HOSTS
    PYTHON_VDR_VDG_HOSTS
)

_interop_utc_now_iso() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

_interop_write_run_json() {
    local subcommand="$1"
    shift
    local repo_root="$SCRIPT_DIR/.."
    local matrix_scenarios_csv="${1:-}"
    shift || true
    python3 - "$INTEROP_REPORT_DIR/run.json" "$subcommand" "$matrix_scenarios_csv" "$@" <<'PY'
import json
import os
import subprocess
import sys
from pathlib import Path

run_json_path = Path(sys.argv[1])
subcommand = sys.argv[2]
matrix_csv = sys.argv[3] if len(sys.argv) > 3 else ""
catalog_args = sys.argv[4:]

repo_root = Path(os.environ["INTEROP_REPO_ROOT"])
interop_dir = Path(os.environ["INTEROP_SCRIPT_DIR"])
run_id = os.environ["INTEROP_RUN_ID"]
started_at = os.environ["INTEROP_STARTED_AT"]
argv_v = json.loads(os.environ["INTEROP_RUN_ARGV_JSON"])
invocation = os.environ.get("INTEROP_INVOCATION", subcommand)
zkred_pin = os.environ.get("INTEROP_ZKRED_PIN", "unknown")

env_whitelist = json.loads(os.environ["INTEROP_ENV_WHITELIST_JSON"])
env_m = {}
for key in env_whitelist:
    val = os.environ.get(key)
    if val is not None and val != "":
        env_m[key] = val

def git_cmd(*args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None

git_sha = git_cmd("rev-parse", "HEAD") or "unknown"
git_branch = git_cmd("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
dirty = False
status = git_cmd("status", "--porcelain")
if status:
    dirty = True
catalog_sha = None
spec_dir = interop_dir / "ledgerdomain.github.io" / "did-webplus-spec"
if spec_dir.is_dir():
    proc = subprocess.run(
        ["git", "-C", str(spec_dir), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        catalog_sha = proc.stdout.strip() or None

arch = subprocess.run(["uname", "-m"], capture_output=True, text=True, check=False)
kernel = subprocess.run(["uname", "-sr"], capture_output=True, text=True, check=False)
nproc = subprocess.run(["nproc"], capture_output=True, text=True, check=False)
mem_total_bytes = None
try:
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    for line in meminfo.splitlines():
        if line.startswith("MemTotal:"):
            kb = int(line.split()[1])
            mem_total_bytes = kb * 1024
            break
except OSError:
    pass

docker_ver = subprocess.run(["docker", "--version"], capture_output=True, text=True, check=False)
compose_cmd = os.environ.get("INTEROP_COMPOSE_CMD", "docker compose")
compose_ver = subprocess.run(
    compose_cmd.split() + ["version"],
    capture_output=True,
    text=True,
    check=False,
)

host = {
    "arch": (arch.stdout or "").strip() or None,
    "machine": (arch.stdout or "").strip() or None,
    "kernel": (kernel.stdout or "").strip() or None,
    "cpuCount": int((nproc.stdout or "0").strip() or 0) or None,
    "memTotalBytes": mem_total_bytes,
    "dockerVersion": (docker_ver.stdout or "").strip() or None,
    "composeVersion": (compose_ver.stdout or "").strip() or None,
}

def catalog_resolvers(args: list[str]) -> list[str] | None:
    saw = False
    resolvers: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--resolver":
            saw = True
            val = args[i + 1] if i + 1 < len(args) else ""
            i += 2
        elif arg.startswith("--resolver="):
            saw = True
            val = arg.split("=", 1)[1]
            i += 1
        else:
            i += 1
            continue
        if val == "all":
            return None
        if val in ("python", "rust", "zkred"):
            if val not in resolvers:
                resolvers.append(val)
    if not saw:
        return None
    return resolvers or None

def planned_units() -> list[dict]:
    units: list[dict] = []
    if matrix_csv:
        for part in matrix_csv.split(","):
            part = part.strip()
            if not part:
                continue
            n = int(part)
            units.append(
                {"kind": "matrix", "scenario": n, "suite": f"matrix-{n:02d}"}
            )
    if subcommand in ("vectors", "scenarios", "all"):
        kinds = []
        if subcommand == "all":
            kinds = ["vectors", "scenarios"]
        else:
            kinds = [subcommand]
        for kind in kinds:
            entry: dict = {"kind": kind, "suite": kind}
            if subcommand == kind:
                resolvers = catalog_resolvers(catalog_args)
            else:
                resolvers = None
            if resolvers is not None:
                entry["resolvers"] = resolvers
            units.append(entry)
    return units

payload = {
    "runId": run_id,
    "startedAt": started_at,
    "endedAt": None,
    "invocation": invocation,
    "argv": argv_v,
    "env": env_m,
    "host": host,
    "git": {
        "sha": git_sha,
        "branch": git_branch,
        "dirty": dirty,
        "catalogSubmoduleSha": catalog_sha,
    },
    "zkredPin": zkred_pin,
    "plannedUnits": planned_units(),
}

run_json_path.parent.mkdir(parents=True, exist_ok=True)
with run_json_path.open("w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

_interop_patch_run_json_ended_at() {
    python3 - "$INTEROP_REPORT_DIR/run.json" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
data["endedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
with path.open("w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, sort_keys=True)
    fh.write("\n")
PY
}

interop_report_init() {
    local subcommand="$1"
    shift
    if [[ -n "${INTEROP_REPORT_DIR:-}" ]]; then
        return 0
    fi
    detect_compose
    RUN_ID="$(date -u +%Y-%m-%dT%H.%M.%SZ)"
    INTEROP_STARTED_AT="$(_interop_utc_now_iso)"
    INTEROP_REPORT_DIR="$SCRIPT_DIR/reports/$RUN_ID"
    INTEROP_CONTAINER_REPORT_DIR="/app/interop/reports/$RUN_ID"
    mkdir -p "$INTEROP_REPORT_DIR/suites" "$INTEROP_REPORT_DIR/logs"
    ln -sfn "$RUN_ID" "$SCRIPT_DIR/reports/latest"

    local matrix_csv=""
    local -a catalog_args_v=()
    case "$subcommand" in
        matrix)
            if [[ $# -gt 0 && "$1" =~ ^(1[0-9]|2[0-2]|[1-9])$ ]]; then
                matrix_csv="$1"
            else
                matrix_csv="$(seq -s, 1 22)"
            fi
            ;;
        vectors|scenarios)
            catalog_args_v=("$@")
            ;;
        all)
            matrix_csv="$(seq -s, 1 22)"
            ;;
    esac

    local env_json="["
    local first=1
    local key
    for key in "${INTEROP_ENV_WHITELIST[@]}"; do
        if [[ $first -eq 0 ]]; then
            env_json+=","
        fi
        env_json+=$(python3 -c "import json; print(json.dumps('$key'))")
        first=0
    done
    env_json+="]"

    export INTEROP_REPO_ROOT="$SCRIPT_DIR/.."
    export INTEROP_SCRIPT_DIR="$SCRIPT_DIR"
    export INTEROP_RUN_ID="$RUN_ID"
    export INTEROP_STARTED_AT
    export INTEROP_RUN_ARGV_JSON="$RUN_SH_ORIGINAL_ARGV_JSON"
    export INTEROP_INVOCATION="$subcommand"
    export INTEROP_ZKRED_PIN="$(pinned_ts_version)"
    export INTEROP_ENV_WHITELIST_JSON="$env_json"
    export INTEROP_COMPOSE_CMD="$COMPOSE"

    _interop_write_run_json "$subcommand" "$matrix_csv" "${catalog_args_v[@]}"
}

interop_report_finalize() {
    local exit_code="${1:-0}"
    if [[ "${INTEROP_REPORT_SKIP_FINALIZE:-}" == 1 ]]; then
        return "$exit_code"
    fi
    if [[ -z "${INTEROP_REPORT_DIR:-}" ]]; then
        return "$exit_code"
    fi
    _interop_patch_run_json_ended_at
    if ! python3 "$SCRIPT_DIR/report.py" "$INTEROP_REPORT_DIR"; then
        echo "Warning: report.py failed (see above); partial artifacts in $INTEROP_REPORT_DIR" >&2
    fi
    echo ""
    echo "Interop report: $INTEROP_REPORT_DIR/report.md"
    return "$exit_code"
}

build_python_cli_image() {
    echo "Building Python CLI resolver image (did-webplus-python-cli)..."
    docker build -f Dockerfile.python-cli -t did-webplus-python-cli ..
}

build_resolver_images() {
    local need_python="${1:-0}"
    local need_zkred="${2:-0}"
    if [[ "$need_python" -eq 1 ]]; then
        build_python_cli_image
    fi
    if [[ "$need_zkred" -eq 1 ]]; then
        build_zkred_image
    fi
}

# Rust resolver uses a pre-pulled ghcr.io image; only python-cli and zkred are built locally.
catalog_runner_image_needs() {
    local need_python=0
    local need_zkred=0
    local saw_resolver=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --resolver)
                saw_resolver=1
                case "${2:-}" in
                    all)
                        need_python=1
                        need_zkred=1
                        ;;
                    python) need_python=1 ;;
                    zkred) need_zkred=1 ;;
                    rust) ;;
                    *)
                        echo "Error: unknown --resolver value: ${2:-}" >&2
                        exit 1
                        ;;
                esac
                shift 2
                ;;
            --resolver=*)
                saw_resolver=1
                local r="${1#--resolver=}"
                case "$r" in
                    all)
                        need_python=1
                        need_zkred=1
                        ;;
                    python) need_python=1 ;;
                    zkred) need_zkred=1 ;;
                    rust) ;;
                    *)
                        echo "Error: unknown --resolver value: $r" >&2
                        exit 1
                        ;;
                esac
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    if [[ "$saw_resolver" -eq 0 ]]; then
        need_python=1
        need_zkred=1
    fi
    echo "$need_python $need_zkred"
}

matrix_scenario_image_needs() {
    local n="$1"
    local need_python=0
    local need_zkred=0
    if [[ "$n" -ge 17 && "$n" -le 20 ]]; then
        need_zkred=1
    elif [[ "$n" -eq 21 || "$n" -eq 22 ]]; then
        need_python=1
        need_zkred=1
    else
        local n0=$((n - 1))
        if (( (n0 & 2) == 0 )); then
            need_python=1
        fi
    fi
    echo "$need_python $need_zkred"
}

build_zkred_image() {
    echo "Building zkred runner image (did-webplus-zkred)..."
    if [[ -n "${INTEROP_ZKRED_DID_WEBPLUS_VERSION:-}" ]]; then
        echo "=== TS version override: $INTEROP_ZKRED_DID_WEBPLUS_VERSION (lockfile unchanged) ==="
        local spec
        if [[ "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == github:* || "$INTEROP_ZKRED_DID_WEBPLUS_VERSION" == git+* ]]; then
            spec="$INTEROP_ZKRED_DID_WEBPLUS_VERSION"
        else
            spec="@zkred/did-webplus@${INTEROP_ZKRED_DID_WEBPLUS_VERSION}"
        fi
        docker build -t did-webplus-zkred --build-arg "ZKRED_SPEC=$spec" -f - . <<'EOF'
FROM node:20-slim
ARG ZKRED_SPEC
WORKDIR /app
COPY ts_runner.mjs ./
RUN npm init -y && npm install --ignore-scripts --save "$ZKRED_SPEC"
ENTRYPOINT ["node", "ts_runner.mjs"]
EOF
    else
        docker build -f Dockerfile.zkred -t did-webplus-zkred .
    fi
}

cmd_clean() {
    detect_compose
    $COMPOSE down -v
    docker run --rm \
        -v "$SCRIPT_DIR:/interop" \
        alpine:3.20 \
        sh -c 'rm -rf /interop/wallets /interop/wallet_dir_scenario_*'
    mkdir -p "$SCRIPT_DIR/wallets"
}

ensure_catalog() {
    if [[ ! -f "$CATALOG_INDEX" ]]; then
        echo "Error: test-vector catalog missing at $CATALOG_INDEX"
        echo "Initialize the did-webplus-spec submodule (see resolver-conformance-testing.md):"
        echo "  git submodule update --init interop/ledgerdomain.github.io/did-webplus-spec"
        exit 1
    fi
}

wait_for_catalog_healthy() {
    $COMPOSE up -d --build "$SERVICE"
    local service_container_id
    service_container_id="$($COMPOSE ps -q "$SERVICE")"
    if [[ -z "$service_container_id" ]]; then
        echo "Error: failed to get container id for $SERVICE"
        $COMPOSE ps
        exit 1
    fi
    echo "Waiting for $SERVICE to be healthy..."
    local start_seconds now_seconds elapsed_seconds health_status
    start_seconds="$(date +%s)"
    while true; do
        health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$service_container_id" 2>/dev/null || true)"
        case "$health_status" in
            healthy) break ;;
            unhealthy|exited|dead)
                echo "Error: $SERVICE health status is $health_status"
                $COMPOSE logs "$SERVICE" || true
                exit 1
                ;;
        esac
        now_seconds="$(date +%s)"
        elapsed_seconds="$((now_seconds - start_seconds))"
        if [[ "$elapsed_seconds" -ge "$HEALTH_TIMEOUT_SECONDS" ]]; then
            echo "Error: timed out waiting for $SERVICE to become healthy (${HEALTH_TIMEOUT_SECONDS}s)"
            $COMPOSE ps
            $COMPOSE logs "$SERVICE" || true
            exit 1
        fi
        sleep 1
    done
}

wait_for_catalog_control_api() {
    echo "Verifying catalog control API (GET /health)..."
    local start_seconds now_seconds elapsed_seconds
    start_seconds="$(date +%s)"
    while true; do
        if python3 - <<'PY' 2>/dev/null
import json
import sys
import urllib.request

with urllib.request.urlopen("http://127.0.0.1:80/health", timeout=2) as resp:
    payload = json.loads(resp.read().decode("utf-8"))
if not payload.get("ok") or not payload.get("controlApi"):
    sys.exit(1)
PY
        then
            return 0
        fi
        now_seconds="$(date +%s)"
        elapsed_seconds="$((now_seconds - start_seconds))"
        if [[ "$elapsed_seconds" -ge "$HEALTH_TIMEOUT_SECONDS" ]]; then
            echo "Error: catalog control API not ready (GET /health must report controlApi)"
            $COMPOSE logs "$SERVICE" || true
            exit 1
        fi
        sleep 1
    done
}

run_catalog_suite() {
    local runner_module="$1"
    shift
    local image_needs need_python need_zkred
    image_needs="$(catalog_runner_image_needs "$@")"
    read -r need_python need_zkred <<<"$image_needs"
    ensure_catalog
    detect_compose
    build_resolver_images "$need_python" "$need_zkred"
    echo "Starting $SERVICE..."
    wait_for_catalog_healthy
    wait_for_catalog_control_api
    echo "Building test-vector-runner image..."
    $COMPOSE build test-vector-runner
    echo "Streaming Docker service logs (background)..."
    $COMPOSE logs -f "$SERVICE" &
    local log_pid=$!
    local exit_code=1
    teardown_catalog() {
        kill "$log_pid" 2>/dev/null || true
        cd "$SCRIPT_DIR"
        $COMPOSE down
    }
    trap teardown_catalog EXIT
    local suite_id=""
    case "$runner_module" in
        run_test_vectors.py) suite_id="vectors" ;;
        run_resolution_scenarios.py) suite_id="scenarios" ;;
        *)
            echo "Error: unknown catalog runner module: $runner_module" >&2
            return 1
            ;;
    esac
    local report_json_container=""
    local log_file=""
    if [[ -n "${INTEROP_REPORT_DIR:-}" ]]; then
        report_json_container="${INTEROP_CONTAINER_REPORT_DIR}/suites/${suite_id}.json"
        log_file="$INTEROP_REPORT_DIR/logs/${suite_id}.log"
    fi
    echo "Running $runner_module..."
    set +e
    if [[ -n "$report_json_container" ]]; then
        $COMPOSE run --rm --entrypoint uv test-vector-runner \
            run python "interop/${runner_module}" "$@" \
            --report-json "$report_json_container" \
            2>&1 | tee "$log_file"
    else
        $COMPOSE run --rm --entrypoint uv test-vector-runner \
            run python "interop/${runner_module}" "$@"
    fi
    exit_code=${PIPESTATUS[0]}
    set -e
    trap - EXIT
    teardown_catalog
    return "$exit_code"
}

derive_compose_vdr_vdg() {
    local n="$1"
    if [[ "$n" -ge 17 ]]; then
        case "$n" in
            17) USE_VDG=0; VDR_RUST=0 ;;
            18) USE_VDG=1; VDR_RUST=0 ;;
            19) USE_VDG=0; VDR_RUST=1 ;;
            20) USE_VDG=1; VDR_RUST=1 ;;
            21) USE_VDG=0; VDR_RUST=0 ;;
            22) USE_VDG=0; VDR_RUST=1 ;;
        esac
    else
        USE_VDG=$(( (n - 1) & 1 ))
        VDR_RUST=$(( ((n - 1) & 4) != 0 ))
    fi
}

start_matrix_services() {
    local scenario="$1"
    derive_compose_vdr_vdg "$scenario"
    if [[ $VDR_RUST -eq 1 ]]; then
        if [[ $USE_VDG -eq 1 ]]; then
            echo "Starting Rust VDR + VDG..."
            RUST_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d rust-vdr-db rust-vdg-db rust-vdg rust-vdr
        else
            echo "Starting Rust VDR..."
            RUST_VDR_VDG_HOSTS= $COMPOSE up -d rust-vdr-db rust-vdr
        fi
    else
        if [[ $USE_VDG -eq 1 ]]; then
            echo "Starting Python VDR + Rust VDG..."
            PYTHON_VDR_VDG_HOSTS=rust-vdg:8086 $COMPOSE up -d --build rust-vdg-db rust-vdg python-vdr
        else
            echo "Starting Python VDR..."
            $COMPOSE up -d --build python-vdr
        fi
    fi
}

run_matrix_scenario() {
    local scenario="$1"
    local pinned_ts log_pid image_needs need_python need_zkred
    local suite_id report_json_container log_file runner_exit
    pinned_ts="$(pinned_ts_version)"
    image_needs="$(matrix_scenario_image_needs "$scenario")"
    read -r need_python need_zkred <<<"$image_needs"
    suite_id="$(printf 'matrix-%02d' "$scenario")"
    detect_compose
    echo "=== Scenario $scenario ==="
    cmd_clean
    build_resolver_images "$need_python" "$need_zkred"
    if [[ "$scenario" -ge 17 ]]; then
        echo "=== TS interop: @zkred/did-webplus $pinned_ts (from package-lock.json) ==="
        echo "=== Version management: see interop/README.md or interop/ZKRED_VERSION.md ==="
    fi
    start_matrix_services "$scenario"
    echo "Streaming Docker service logs (background)..."
    $COMPOSE logs -f &
    log_pid=$!
    echo "Waiting for services to be healthy..."
    sleep 3
    report_json_container=""
    log_file=""
    if [[ -n "${INTEROP_REPORT_DIR:-}" ]]; then
        report_json_container="${INTEROP_CONTAINER_REPORT_DIR}/suites/${suite_id}.json"
        log_file="$INTEROP_REPORT_DIR/logs/${suite_id}.log"
    fi
    set +e
    if [[ -n "$report_json_container" ]]; then
        $COMPOSE run --rm --build interop-runner "$scenario" \
            --report-json "$report_json_container" \
            2>&1 | tee "$log_file"
    else
        $COMPOSE run --rm --build interop-runner "$scenario" 2>&1 | tee "${log_file:-/dev/null}"
    fi
    runner_exit=${PIPESTATUS[0]}
    set -e
    if [[ "$runner_exit" -eq 0 ]]; then
        kill "$log_pid" 2>/dev/null || true
        $COMPOSE down
        return 0
    fi
    kill "$log_pid" 2>/dev/null || true
    $COMPOSE down
    return 1
}

cmd_matrix() {
    local scenario="${1:-}"
    if [[ -n "$scenario" ]]; then
        if [[ ! "$scenario" =~ ^(1[0-9]|2[0-2]|[1-9])$ ]]; then
            echo "Error: matrix scenario must be 1–22"
            usage
            exit 1
        fi
        interop_report_init matrix "$scenario"
        run_matrix_scenario "$scenario"
        local ec=$?
        interop_report_finalize "$ec"
        return "$ec"
    fi
    interop_report_init matrix
    local pinned_ts failed=0
    pinned_ts="$(pinned_ts_version)"
    echo "Scenarios 1-16: Python/Rust matrix"
    echo "Scenarios 17-22: @zkred/did-webplus (TS)"
    echo "Pinned TS version: $pinned_ts"
    local s results=()
    for s in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22; do
        echo ""
        echo "=============================================="
        echo "  Scenario $s"
        echo "=============================================="
        if run_matrix_scenario "$s"; then
            results+=("  Scenario $s: PASSED")
        else
            results+=("  Scenario $s: FAILED")
            failed=1
        fi
    done
    echo ""
    echo "=============================================="
    if [[ $failed -eq 0 ]]; then
        echo "  All matrix scenarios PASSED"
    else
        echo "  One or more matrix scenarios FAILED"
    fi
    echo "=============================================="
    for line in "${results[@]}"; do
        echo "$line"
    done
    interop_report_finalize "$failed"
    [[ $failed -eq 0 ]]
}

cmd_vectors() {
    interop_report_init vectors "$@"
    local ec=0
    run_catalog_suite run_test_vectors.py "$@" || ec=$?
    interop_report_finalize "$ec"
    return "$ec"
}

cmd_scenarios() {
    interop_report_init scenarios "$@"
    local ec=0
    run_catalog_suite run_resolution_scenarios.py "$@" || ec=$?
    interop_report_finalize "$ec"
    return "$ec"
}

cmd_all() {
    interop_report_init all
    INTEROP_REPORT_SKIP_FINALIZE=1
    local failed=0
    cmd_matrix || failed=1
    cmd_vectors || failed=1
    cmd_scenarios || failed=1
    unset INTEROP_REPORT_SKIP_FINALIZE
    interop_report_finalize "$failed"
    return "$failed"
}

SUB="${1:-}"
shift || true
case "$SUB" in
    matrix) cmd_matrix "$@"; exit $? ;;
    vectors) cmd_vectors "$@"; exit $? ;;
    scenarios) cmd_scenarios "$@"; exit $? ;;
    all) cmd_all; exit $? ;;
    clean) cmd_clean ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    "")
        usage
        exit 1
        ;;
    *)
        echo "Unknown subcommand: $SUB"
        usage
        exit 1
        ;;
esac
