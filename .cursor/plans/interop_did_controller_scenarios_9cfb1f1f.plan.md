---
name: Interop DID controller scenarios
overview: Extend interop tests to drive create/update via either the Python or Rust DID controller instead of fixture-driven HTTP POST/PUT. Use 16 exhaustive scenarios from 4 binary axes (controller, VDR, resolver, VDG on/off), with a clean wallet directory per run and updated docs/logging.
todos: []
isProject: false
---

# Interop: Add DID controller dimension (Python vs Rust)

## Current state

- **Scenarios 1–4** in [interop/run_interop_tests.py](interop/run_interop_tests.py): combination of **resolver** (Python vs Rust) and **VDR/VDG** (Rust VDR, Python VDR, with or without Rust VDG).
- Create/update are done **by hand**: [make_root_doc_with_key](interop/run_interop_tests.py) and [make_update_doc_with_key](interop/run_interop_tests.py) build JCS, then `httpx.post(url, content=root_jcs)` and `httpx.put(url, content=update_jcs)`.
- **Rust CLI** is already used for the resolver in scenarios 3–4 via `RUST_CLI_IMAGE` and `docker run ... did resolve`.

## Goal

- **Controller** becomes a dimension: **Python** (this repo) or **Rust** (Docker `ghcr.io/ledgerdomain/did-webplus-cli:v0.1.0`).
- Create and update are performed **only** via the chosen controller’s CLI (no direct POST/PUT or in-process doc building for create/update).
- **16 scenarios** total: exhaustive combination of 4 binary axes — (1) DID controller: Python vs Rust, (2) VDR: Python vs Rust, (3) DID resolver: Python vs Rust, (4) VDG: without Rust VDG vs with Rust VDG.
- **Wallet directory**: one temp directory per scenario run, cleared (or created empty) before the run, used as the controller’s wallet/base dir for the whole scenario.

## Controller CLI usage


| Action | Python                                                                                                                    | Rust (Docker)                                                                                                                                                                                    |
| ------ | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Create | `uv run did-webplus did create <vdr-create-endpoint> --base-dir <wallet_dir> [--http-scheme-override ...]` → stdout = DID | `docker run --rm -v <wallet_dir>:/root/.did-webplus --network host -e DID_WEBPLUS_HTTP_SCHEME_OVERRIDE=... RUST_CLI_IMAGE wallet did create --vdr <vdr-create-endpoint>` → parse DID from stdout |
| Update | `uv run did-webplus did update <did> --base-dir <wallet_dir> [--http-scheme-override ...]`                                | `docker run --rm -v <wallet_dir>:/root/.did-webplus --network host ... RUST_CLI_IMAGE wallet did update` (no DID arg per user; if Rust CLI requires DID, add it)                                 |


- **VDR create endpoints**: Rust VDR: `http://rust-vdr:8085`, Python VDR: `http://python-vdr:8087`. Same as current base URLs used for POST.
- **HTTP scheme overrides**: Pass the same overrides as today (`rust-vdr=http,rust-vdg=http,python-vdr=http`) so that resolution URLs use `http` for these hostnames. For Python: `--http-scheme-override`. For Rust Docker: `-e DID_WEBPLUS_HTTP_SCHEME_OVERRIDE=...` (confirm Rust CLI env name; align with existing resolver usage in [run_rust_resolve](interop/run_interop_tests.py)).

## Scenario matrix (16 scenarios)

Four independent binary axes: **Controller** (Python / Rust), **VDR** (Python / Rust), **Resolver** (Python / Rust), **VDG** (no / yes = Rust VDG in front of VDR). 2×2×2×2 = 16 scenarios.


| #   | Controller | VDR    | Resolver | VDG |
| --- | ---------- | ------ | -------- | --- |
| 1   | Python     | Python | Python   | no  |
| 2   | Python     | Python | Python   | yes |
| 3   | Python     | Python | Rust     | no  |
| 4   | Python     | Python | Rust     | yes |
| 5   | Python     | Rust   | Python   | no  |
| 6   | Python     | Rust   | Python   | yes |
| 7   | Python     | Rust   | Rust     | no  |
| 8   | Python     | Rust   | Rust     | yes |
| 9   | Rust       | Python | Python   | no  |
| 10  | Rust       | Python | Python   | yes |
| 11  | Rust       | Python | Rust     | no  |
| 12  | Rust       | Python | Rust     | yes |
| 13  | Rust       | Rust   | Python   | no  |
| 14  | Rust       | Rust   | Python   | yes |
| 15  | Rust       | Rust   | Rust     | no  |
| 16  | Rust       | Rust   | Rust     | yes |


## Implementation steps

### 1. Wallet directory and controller helpers in [interop/run_interop_tests.py](interop/run_interop_tests.py)

- At the start of each scenario run, create a **temporary directory** (e.g. `tempfile.mkdtemp()` or a fixed `interop/wallet_scratch`) and use it as the wallet/base path. If reusing a fixed path, clear it (remove contents or recreate) so each run starts from a clean slate.
- Add two helper functions (or a small internal abstraction):
  - `**_run_python_controller_create(vdr_create_endpoint: str, wallet_dir: Path) -> str`**  
  Run `uv run did-webplus did create <vdr_create_endpoint> --base-dir <wallet_dir> --http-scheme-override ...` from the repo root; return stdout.strip() as the created DID. Raise or return failure so the scenario can fail clearly.
  - `**_run_python_controller_update(did: str, wallet_dir: Path) -> None`**  
  Run `uv run did-webplus did update <did> --base-dir <wallet_dir> --http-scheme-override ...`. Check return code.
  - `**_run_rust_controller_create(vdr_create_endpoint: str, wallet_dir: Path) -> str`**  
  Run `docker run --rm -v <wallet_dir>:/root/.did-webplus --network host` with env for HTTP overrides, `RUST_CLI_IMAGE`, args `wallet did create --vdr <vdr_create_endpoint>`. Parse DID from stdout (e.g. last line or line containing `did:webplus:`).
  - `**_run_rust_controller_update(wallet_dir: Path, did: str) -> None`**  
  Run `docker run ... wallet did update`; if the Rust CLI requires the DID, pass it as `--did <did>` (e.g. `--did did:webplus:example.com:uHiXXXX`). See section 6.

Use the same `RUST_CLI_IMAGE` constant and `--network host` pattern as in [run_rust_resolve](interop/run_interop_tests.py) so behavior is consistent.

### 2. Replace fixture-driven create/update with controller-driven flow

- **Remove** (or stop using in the interop flow) the direct POST/PUT and the helpers **make_root_doc_with_key** and **make_update_doc_with_key** for the scenario execution path. Optionally keep them only for backward compatibility or remove entirely if unused elsewhere in this file.
- For each scenario, the flow becomes:
  1. Ensure wallet dir is clean (temp or cleared).
  2. **Create**: Call either Python or Rust controller create with the VDR endpoint for the chosen VDR (Rust VDR: `http://rust-vdr:8085`, Python VDR: `http://python-vdr:8087`). Obtain `did` from create output.
  3. **Resolve after create**: Run the chosen resolver (Python or Rust) on `did` with optional VDG URL. Assert resolved document has versionId=0 (root). When VDG is used, run the appropriate VDG header checks for this resolution.
  4. **Update**: Call either Python or Rust controller update with `did` (and wallet dir). For Rust, if the CLI requires the DID, pass it (e.g. `--did <did>`); see section 6.
  5. **Verify VDR**: GET the resolution URL (same as today) and assert response contains the updated document (e.g. versionId=1 / expected selfHash).
  6. **Resolve after update**: Run the chosen resolver again on `did`. Assert versionId=1 and, when VDG is used, run the existing VDG header checks (e.g. X-DID-Webplus-VDG-Cache-Hit for plain DID vs versionId param).

Keep the existing **resolution_path(did)** and **assert_vdg_headers** usage; only the source of `did` and the way create/update are performed change.

### 3. Unify scenario execution and 16-scenario mapping

- Refactor the current scenario functions into a **single parameterized flow** that takes:
  - `controller_kind: "python" | "rust"`
  - `vdr_kind: "python" | "rust"` (determines VDR base URL and create endpoint)
  - `resolver_kind: "python" | "rust"`
  - `use_vdg: bool` (if True, use Rust VDG URL in front of the VDR for resolution)
- In `main()`, map scenario numbers **1–16** to (controller, vdr, resolver, vdg) per the matrix above. One simple mapping: scenario index `n` (1-based) → bits or a lookup table for the four axes. Call the unified flow with a fresh wallet dir for each scenario.
- Log clearly all four dimensions (e.g. “Scenario 7: Python controller, Rust VDR, Rust resolver, no VDG”).

### 4. CLI and script invocation; service startup

- **Service startup**: For each scenario, start the VDR and optionally VDG from the scenario’s axes (vdr_kind, use_vdg). Shell scripts can derive these from the scenario number and run the correct `docker compose up` set (Rust VDR only, Rust VDR+VDG, Python VDR only, Python VDR+VDG).
- **Script entrypoint**: Accept scenario **1–16**. Update [interop/run_interop_tests.sh](interop/run_interop_tests.sh) and [interop/run_all_interop_tests.sh](interop/run_all_interop_tests.sh) to pass 1–16 and to loop over 1–16 in “run all” mode.
- **Docstring and usage**: In [run_interop_tests.py](interop/run_interop_tests.py) top-level docstring and in any `print("Usage: ...")`, document the 16 scenarios and the four axes (Controller, VDR, Resolver, VDG).

### 5. Summary logging and README

- **Summary block**: For each scenario, after “All tests PASSED”, log a short summary that includes all four axes (controller, VDR, resolver, VDG). Use a **single parameterized summary** (e.g. one function that takes the four choices and formats the message) instead of 16 if/elifs.
- **README**: In [interop/README.md](interop/README.md):
  - Update the **Test matrix** table to the full 16-row matrix (Controller, VDR, Resolver, VDG).
  - Update **Test details** (and any example output) so that create/update are described as performed by the chosen controller (Python or Rust), not “Test script submitted … by hand”.
  - Under **Docker images**, state that the Rust CLI image is used as **resolver** (when resolver=Rust) and as **DID controller** (when controller=Rust). Mention that the Python controller is this repo’s `did-webplus did create` / `did update` and uses a local wallet directory.
  - Update **Running tests** to show scenarios 1–16 (e.g. `./run_interop_tests.sh 10`) and that each run uses a clean wallet directory for the controller.

### 6. Rust CLI update command (clarification)

- If the Rust CLI requires the DID to be specified for update, it is done using the `**--did`** argument, for example: `--did did:webplus:example.com:uHiXXXX`. Implement `**_run_rust_controller_update`** to pass `--did <did>` (the DID returned from create) when the CLI expects it.

## Files to touch


| File                                                                 | Changes                                                                                                                                                                                                     |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [interop/run_interop_tests.py](interop/run_interop_tests.py)         | Wallet dir; Python/Rust controller create/update helpers; remove or bypass fixture POST/PUT; single parameterized scenario flow; scenario 1–16 mapping (4 axes); parameterized summary log; usage/docstring |
| [interop/run_interop_tests.sh](interop/run_interop_tests.sh)         | Accept 1–16; usage text for 16 scenarios / 4 axes                                                                                                                                                           |
| [interop/run_all_interop_tests.sh](interop/run_all_interop_tests.sh) | Loop 1–16; optional echo for scenario matrix                                                                                                                                                                |
| [interop/README.md](interop/README.md)                               | Test matrix (16 rows, 4 axes); test details and Docker/controller description; run instructions for 1–16                                                                                                    |


## Optional / follow-ups

- If Rust CLI `wallet did update` requires a DID, add it to the Docker invocation and document in README.
- Consider adding a one-line comment in the script pointing to the Rust CLI image tag so it’s easy to bump later.

