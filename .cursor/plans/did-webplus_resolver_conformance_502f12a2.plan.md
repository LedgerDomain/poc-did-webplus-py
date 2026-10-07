---
name: did-webplus resolver conformance
overview: Refactor Python resolution around a pre-fetch locality plan, option-gated metadata, and typed errors, then harden query/validation and byte-range behavior. Verify with unit tests plus every Python-relevant `interop/run.sh` suite, ending with the complete interop run.
todos:
  - id: resolution-model
    content: Add resolution options, RFC 9457 errors, result types, timestamp normalization, and exact metadata builders.
    status: completed
  - id: locality-planner
    content: Implement and unit-test every pre-fetch document and metadata locality rule.
    status: completed
  - id: resolver-flow
    content: Refactor resolver orchestration around the locality plan, one-fetch limit, document selection, and typed failures.
    status: completed
  - id: validation
    content: Harden DID query, chain ID, and verification-method URL validation without regressing the 302 vectors.
    status: completed
  - id: range-storage
    content: Correct JSONL byte offsets, incremental parsing boundaries, HTTP(S) Range requests, and fetch status handling.
    status: completed
  - id: cli-interop
    content: Expose and test all resolution options through the Python CLI and interop adapter.
    status: completed
  - id: verify-all
    content: Make tests hermetic and run every Python unit, vector, scenario, and matrix test to green.
    status: completed
isProject: false
---

# Python did:webplus conformance

## Approach

Make resolution a deterministic pipeline: strictly parse the DID URL and options, inspect the locally verified prefix, freeze the three locality booleans, optionally perform at most one range fetch, select the requested document, and construct only the metadata groups requested by the caller.

The scope is the Python controller, VDR, and resolver. The final full interop run is a regression check, but unrelated failures from the independently pinned Zkred package are not part of this work.

## 1. Resolution data model and output

- Add [`did_webplus/resolution.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/resolution.py) for:
  - `ResolutionOptions` with `requestCreate`, `requestNext`, `requestLatest`, `requestDeactivated`, and `localResolutionOnly`;
  - `LocalityPlan`, holding the pre-fetch requested-document result, metadata-group locality, fetch decision, and the three frozen resolution booleans;
  - an RFC 9457 problem-details type and constants for `INVALID_DID`, `INVALID_DID_URL`, `INVALID_OPTIONS`, `NOT_FOUND`, `INVALID_DID_DOCUMENT`, `INTERNAL_ERROR`, `LOCAL_RESOLUTION_NOT_POSSIBLE`, and `VDR_FETCH_FAILED`;
  - UTC timestamp helpers that preserve at most millisecond precision and floor seconds fields to `YYYY-MM-DDTHH:MM:SSZ`.
- Replace the old fixed metadata dataclass/output in [`did_webplus/resolver.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/resolver.py) with exact wire dictionaries:
  - always emit `versionId` as an ASCII string;
  - emit `updated` and `updatedMilliseconds` only for non-root documents;
  - emit `created` and `createdMilliseconds` only when `requestCreate` is set;
  - emit the complete `nextUpdate`, `nextUpdateMilliseconds`, and `nextVersionId` group only when `requestNext` is set and a successor exists;
  - emit `latestUpdate`, `latestUpdateMilliseconds`, and `latestVersionId` only when `requestLatest` is set;
  - emit `deactivated: true` whenever deactivation is known, but emit `false` only when `requestDeactivated` was requested.
- Correct the wire key to `fetchedUpdatesFromVDR`. On failure, always return `didDocument: null`, `didDocumentMetadata: {}`, an RFC 9457 `error` object, and all three booleans. Keep `contentType: application/did+json` on successful CLI representation output.

## 2. Pre-fetch locality planner

- Add one planner used by every resolution path. It must inspect only the contiguous verified local prefix and freeze these values before any fetch:
  - `didDocumentResolvedLocally`: whether the requested document was already local;
  - `didDocumentMetadataResolvedLocally`: whether every requested metadata group was locally satisfiable; this is vacuously `true` when none are requested;
  - `fetchedUpdatesFromVDR`: whether the plan attempts a VDR/VDG fetch, including a failed or zero-byte fetch.
- Encode each spec rule explicitly:
  - a plain DID requires a fetch even when warm, unless the latest local document is deactivated;
  - a `selfHash`/`versionId`-addressed document can resolve locally when the document and all requested metadata are local;
  - creation metadata is local iff version 0 is present;
  - next metadata is local iff the successor is present or the requested document is deactivated; a non-deactivated local tip requires a fetch to establish absence;
  - latest/deactivated metadata is local iff the latest-known local document is deactivated;
  - a known deactivation proves the true latest document, no successor, and absence of unknown hashes or later versions.
- For both query parameters, compare both targets. A locally detectable conflict must fail as `INVALID_DID_URL` without fetching and with `didDocumentResolvedLocally: false`; otherwise fetch once and repeat the conflict/absence check.
- For `localResolutionOnly`, perform zero network requests. Succeed only if every required document and metadata determination is local; otherwise return `LOCAL_RESOLUTION_NOT_POSSIBLE` while preserving the planner's split locality booleans.

## 3. Resolver orchestration and failures

- Refactor [`FullDIDResolver.resolve`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/resolver.py) into parse -> local snapshot -> locality plan -> optional fetch -> final selection -> metadata construction.
- Perform at most one VDR/VDG microledger request per resolution. Do not revise locality booleans after data arrives.
- Map outcomes precisely:
  - malformed DID/options/query or conflicting query parameters to the corresponding W3C error;
  - absent or empty microledger, missing requested document after fetch, and known absence after deactivation to `NOT_FOUND`;
  - fetched document validation failures to `INVALID_DID_DOCUMENT`;
  - required network failures, including when the requested document was local but metadata forced the fetch, to `VDR_FETCH_FAILED`;
  - unexpected internal exceptions to `INTERNAL_ERROR`.
- Preserve the existing public sync/async entry points and accept `no_fetch` as a compatibility alias for `localResolutionOnly`.

## 4. DID URL and document validation

- Make [`parse_did_with_query`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/did.py) reject fragments, duplicate/blank supported parameters, invalid or negative `versionId`, malformed `selfHash`, and unsupported resolution query forms rather than silently taking the first value.
- In [`did_webplus/document.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/document.py), require every non-root document `id` to equal its predecessor's `id`, retain strict version/timestamp/previous-hash checks, and reject updates after a deactivation tombstone.
- In [`did_webplus/selfhash.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/selfhash.py), validate every verification-method `id` and JWK `kid` as a fully-qualified resource URL with `selfHash` followed by `versionId`, both values matching the containing document, plus the required fragment. Keep root path/controller slot checks.
- Add targeted negative tests before changing validation and rerun all 302 catalog vectors after each validation group so valid cross-implementation documents are not accidentally rejected.

## 5. Incremental JSONL fetching and storage

- Update [`did_webplus/store.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/store.py) so the archived offset denotes the byte immediately after the final `}` of the last verified document, not an assumed trailing newline.
- Update [`did_webplus/http_client.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/http_client.py) to send `Range: bytes=N-` for both HTTP and HTTPS whenever a prefix exists; retain ordinary/zero-based fetching for a cold store.
- Distinguish response handling:
  - accept a valid full `200` only where a full body is expected, preventing duplicate re-ingestion on an ignored Range;
  - accept `206` incremental content and validate its range boundary;
  - treat matching `416 Content-Range: bytes */N` as up-to-date;
  - surface other status, transport, and range inconsistencies as fetch failures.
- Let incremental parsing consume exactly the separator newline at the archived-document boundary while continuing to reject CRLF, interior blank records, multiple separator lines, non-JCS records, and malformed JSON. Cover source files both with and without a trailing newline.
- Keep ingestion atomic: validate the complete fetched suffix against the stored predecessor before writing any new record or byte offset.

## 6. CLI and interop wiring

- Extend [`did_webplus/cli.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/did_webplus/cli.py) with `--creation`, `--next`, `--latest`, `--deactivated`, and `--local-resolution-only`; retain `--no-fetch` as an alias. Build one `ResolutionOptions` value and pass it through sync and async resolver APIs.
- Ensure JSON output and exit status remain stable: exit 0 with the complete resolution result on success and exit 1 with the structured result on failure. Pretty output should render structured error detail without changing JSON.
- In [`interop/resolvers.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/interop/resolvers.py), mark all Python options supported and map every scenario wire option to the matching CLI flag.

## 7. Tests and acceptance

- Add focused tests under [`tests/`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/tests):
  - table-driven locality cases for cold/warm plain DID, hash/version/both query forms, conflicts, next-at-tip, local successor, creation, latest, deactivation, known absence, and all local-only combinations;
  - exact metadata equality for root and non-root timestamps, string version IDs, option gating, and deactivation presence rules;
  - every normative error type and failure shape, including booleans retained across fetch failure and validation failure;
  - HTTP/HTTPS Range headers, 200/206/416 behavior, byte offsets, trailing-newline variants, and atomic rollback;
  - CLI flag-to-option mapping and JSON success/failure output.
- Reproduce all 19 scenario catalogs as either direct unit cases or integration coverage so later scenario steps are exercised even when an earlier step fails.
- Replace the flaky live-network test in [`tests/test_resolver_integration.py`](/home/vdods/files/github/LedgerDomain/poc-did-webplus-py/tests/test_resolver_integration.py) with a hermetic mocked/fixture equivalent. Do not weaken the spec's rejection of genuine blank JSONL records to accommodate the legacy hosted file.
- Verify in increasing scope:
  1. `uv run pytest -q`;
  2. `./run.sh vectors --resolver python` -> 302/302;
  3. `./run.sh scenarios --resolver python` -> 19/19;
  4. every matrix scenario involving the Python controller, VDR, or resolver;
  5. `./run.sh all` as a cross-implementation regression report.
- Completion requires every Python-owned unit, vector, scenario, and matrix result to pass. Do not edit the pinned catalog or relax harness assertions; any remaining full-run failures must be demonstrably confined to the out-of-scope Zkred package.