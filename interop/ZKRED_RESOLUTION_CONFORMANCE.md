# What `@zkred/did-webplus` still has to implement

This note is for the author of [`@zkred/did-webplus`](https://github.com/Zkred/did-methods/tree/main/packages/did-webplus). It describes the resolution-scenario failures against package **0.10.0**, and the spec behavior the interop suite asserts. The spec is [did:webplus](https://ledgerdomain.github.io/did-webplus-spec/). The oracle is the catalog group `resolution-scenario` (`resolution-scenario.json`, format `did-webplus-resolution-scenario/1`).

The interop harness in this repo now does its part:

- Each resolve runs in a fresh process and is given a directory via `--store-dir`. `ts_runner.mjs` passes that directory to `resolve` as `new FileMicroledgerStore(dir)` from `@zkred/did-webplus/node`. One directory is reused for every step of a scenario, then discarded.
- Success and failure both print one JSON object on stdout: `didDocument` (JSON string), `didDocumentMetadata`, and `didResolutionMetadata`. A resolution error still exits non-zero, but the error object is on stdout where the harness reads it.

`FileMicroledgerStore` does not need to change. The remaining failures are the resolution result the package returns, and resolution options it does not accept. This repo will not patch those inside the package. When `resolve` accepts the options below, the harness will forward them. Until then they stay unsupported, and any scenario step that sets one to `true` fails before the result is compared.

Matrix scenarios 17–20 and the single-document test-vector group can pass without this work. They only check that the latest (or queried) document verifies. The resolution-scenario group checks metadata, locality, and how many times `did-documents.jsonl` is fetched.

## Resolution options

`WebplusResolverOptions` needs these booleans, default `false`:

| Option | Meaning |
|--------|---------|
| `requestCreate` | Include creation metadata (`created`, `createdMilliseconds`). |
| `requestNext` | Include next-update metadata when a successor exists. |
| `requestLatest` | Include latest-update metadata. A plain DID already returns the latest document; this option adds the latest-update fields, and it forces a fetch when the latest document is not known locally. |
| `requestDeactivated` | Include `deactivated`. `true` is emitted whenever the resolved document is a deactivation, even if this option is false. `false` is emitted only when this option is true and the document is not deactivated. When the local tip is not deactivated, this option forces a fetch. |
| `localResolutionOnly` | Do not contact the VDR or VDG. If the document or any requested metadata cannot be determined from the verified local prefix, fail. Do not fall back to the network. |

Query parameters `versionId`, `selfHash`, and `versionTime` already select a document. They are not a substitute for these options.

## `didDocumentMetadata`

Return only the spec fields. Exact key set, exact values. Extra keys fail the comparison.

Omit these fields that 0.10.0 always emits: `mode`, `verified`, `selfHash`, `cached`, and unconditional `created` / `latestVersionId`. `selfHash` stays on the DID document. `created` and `latestVersionId` appear only under the rules below, and `latestVersionId` is paired with `latestUpdate` / `latestUpdateMilliseconds`, not emitted alone.

`versionId` is an ASCII string (`"3"`), not a number.

Timestamps come from `validFrom`. Non-root documents carry two forms:

- `updated`: `validFrom` floored to whole seconds, `YYYY-MM-DDTHH:MM:SSZ`.
- `updatedMilliseconds`: `validFrom` normalized to millisecond precision, with trailing fractional zeros stripped (`2025-01-01T00:00:03.875Z`, `2025-01-01T00:00:00.001Z`).

The root document (versionId 0) has no `updated` or `updatedMilliseconds`.

Presence:

| Fields | When |
|--------|------|
| `versionId` | Always. |
| `updated`, `updatedMilliseconds` | Resolved document is not the root. |
| `created`, `createdMilliseconds` | `requestCreate` is true. Both come from the root document's `validFrom`, with the same second / millisecond split. |
| `nextUpdate`, `nextUpdateMilliseconds`, `nextVersionId` | `requestNext` is true and a successor document exists. Omit the whole group when the resolved document is the latest. `nextVersionId` is a string. |
| `latestUpdate`, `latestUpdateMilliseconds`, `latestVersionId` | `requestLatest` is true. Times come from the latest document's `validFrom`. `latestVersionId` is a string. This is not the same as copying `versionId` into `latestVersionId` on every resolve. |
| `deactivated: true` | The resolved document is a deactivation (`updateRules` empty / tombstone), whether or not `requestDeactivated` was set. |
| `deactivated: false` | `requestDeactivated` is true and the resolved document is not a deactivation. Omit `deactivated` otherwise. |

Examples the catalog expects:

Cold plain DID, no options, latest document is version 3:

```json
{
  "versionId": "3",
  "updated": "2025-01-01T00:00:03Z",
  "updatedMilliseconds": "2025-01-01T00:00:03.875Z"
}
```

Root only (version 0), no options:

```json
{ "versionId": "0" }
```

`requestCreate` on a version-3 document:

```json
{
  "versionId": "3",
  "updated": "2025-01-01T00:00:03Z",
  "updatedMilliseconds": "2025-01-01T00:00:03.875Z",
  "created": "2025-01-01T00:00:00Z",
  "createdMilliseconds": "2025-01-01T00:00:00.001Z"
}
```

`requestNext` when version 1 is resolved and version 2 exists:

```json
{
  "versionId": "1",
  "updated": "2025-01-01T00:00:01Z",
  "updatedMilliseconds": "2025-01-01T00:00:01.633Z",
  "nextUpdate": "2025-01-01T00:00:02Z",
  "nextUpdateMilliseconds": "2025-01-01T00:00:02.242Z",
  "nextVersionId": "2"
}
```

`requestLatest` when version 1 is resolved and version 3 is latest:

```json
{
  "versionId": "1",
  "updated": "2025-01-01T00:00:01Z",
  "updatedMilliseconds": "2025-01-01T00:00:01.633Z",
  "latestUpdate": "2025-01-01T00:00:03Z",
  "latestUpdateMilliseconds": "2025-01-01T00:00:03.875Z",
  "latestVersionId": "3"
}
```

`requestDeactivated` on the root, DID not deactivated:

```json
{ "versionId": "0", "deactivated": false }
```

Deactivated latest document, option not required:

```json
{
  "deactivated": true,
  "updated": "2025-01-01T00:00:03Z",
  "updatedMilliseconds": "2025-01-01T00:00:03.875Z",
  "versionId": "3"
}
```

0.10.0 instead returns objects like:

```json
{
  "created": "2025-01-01T00:00:00.001Z",
  "latestVersionId": "3",
  "mode": "full",
  "selfHash": "uHi…",
  "updated": "2025-01-01T00:00:03.875Z",
  "verified": true,
  "versionId": "3"
}
```

`updated` is the raw `validFrom`, `created` is unconditional, and `mode` / `verified` / `selfHash` are not DID document metadata.

## `didResolutionMetadata`

On success:

```json
{
  "contentType": "application/did+json",
  "fetchedUpdatesFromVDR": true,
  "didDocumentResolvedLocally": false,
  "didDocumentMetadataResolvedLocally": true
}
```

`contentType` is present only on success. The three booleans are always present, on success and on failure.

- `didDocumentResolvedLocally`: the selected document was already in the verified local prefix. A plain DID (no `versionId` / `selfHash` / `versionTime`) is never resolved locally, because "latest" is not known without a fetch unless the local tip is a deactivation.
- `didDocumentMetadataResolvedLocally`: every metadata field in the result was determined from the local prefix, including fields added by the resolution options. Vacuous metadata (nothing was requested beyond `versionId` / `updated`) is local. `requestCreate` on a cold resolve is not local. `requestNext` or `requestLatest` or `requestDeactivated` is not local when the local prefix cannot prove the answer.
- `fetchedUpdatesFromVDR`: this resolution performed a VDR or VDG microledger fetch. Historical queries that the local prefix can answer completely are `false` and produce zero HTTP GETs. A plain DID whose latest local document is not deactivated is `true` even when that document was seen before.

Decide these three booleans from the local prefix **before** the fetch. Do not revise them after bytes arrive.

0.10.0 returns `{ "contentType": "application/did+json" }` and nothing else.

On failure, `didDocument` is null, `didDocumentMetadata` is `{}`, `contentType` is omitted, and `error` is an RFC 9457 object:

```json
{
  "didResolutionMetadata": {
    "error": {
      "type": "https://www.w3.org/ns/did#NOT_FOUND",
      "title": "Not Found",
      "detail": "DID resolution for <did-query> failed"
    },
    "fetchedUpdatesFromVDR": true,
    "didDocumentResolvedLocally": false,
    "didDocumentMetadataResolvedLocally": true
  },
  "didDocument": null,
  "didDocumentMetadata": {}
}
```

The current interop oracle only requires `error` to be present. The spec shape is still the object above, which is what the Python and Rust resolvers emit. A did-resolver string code such as `"notFound"` is not that object.

Error `type` values used by the scenarios:

| Situation | `type` |
|-----------|--------|
| Queried version or self-hash does not exist, including a version the VDR has not served, and known absence after a local deactivation | `https://www.w3.org/ns/did#NOT_FOUND` |
| `versionId` and `selfHash` in the same query name different local documents | `https://www.w3.org/ns/did#INVALID_DID_URL` |
| `localResolutionOnly` and the document or requested metadata is not in the local prefix | `https://ledgerdomain.github.io/did-webplus-spec#LOCAL_RESOLUTION_NOT_POSSIBLE` |
| VDR fetch failed and the local prefix cannot answer | `https://ledgerdomain.github.io/did-webplus-spec#VDR_FETCH_FAILED` |
| Microledger failed verification | `https://www.w3.org/ns/did#INVALID_DID_DOCUMENT` |

Titles: `Not Found`, `Invalid DID URL`, `Local Resolution Not Possible`, `VDR Fetch Failed`, `Invalid DID Document`.

`detail` text is advisory in the current oracle. `type` and the booleans are the contract.

## Fetch behavior

`vdrRequestCount` is the number of GETs of that DID's `did-documents.jsonl` during the step. With `FileMicroledgerStore` wired, a warm process can do a `Range` continuation or no GET at all. Scenarios that still fail after the metadata shape is fixed will be these:

- Plain DID, latest document not deactivated: always one fetch, even if the store already has that document (`plain-did-always-fetches`).
- After a cold fetch, `?selfHash=` or `?versionId=` that the store already holds: zero fetches (`warm-self-hash`, `warm-version-id`).
- First resolve sees one document; the next resolve of the same plain DID, once the VDR serves the rest, is a single range GET from the byte after the last archived `}` (`incremental-range-fetch`). 0.10.0 already does this when the store survives the process.
- `localResolutionOnly` on an empty store: error `LOCAL_RESOLUTION_NOT_POSSIBLE`, zero fetches. After a warm fetch, a version the store holds succeeds with zero fetches. A plain DID, or `requestLatest`, still errors in local-only mode when the tip is not deactivated (`local-only-matrix`).
- `?versionId=` past the served microledger: one fetch, then `NOT_FOUND` (`version-beyond-served`). Do not return an earlier document.
- VDR returns an error and the store already has the selected document: succeed from the store (`fetch-failed-with-local-document`). If it does not, fail with `VDR_FETCH_FAILED` and do not pretend the fetch succeeded.
- A local deactivation proves later versions and unknown self-hashes do not exist: `NOT_FOUND` with zero fetches (`deactivated-known-absence`).

## What to do in the package

1. Accept the five options on `resolve` / `WebplusResolverOptions`.
2. Build `didDocumentMetadata` with the presence rules above. Stop emitting `mode`, `verified`, `selfHash`, and `cached` there.
3. Set the three resolution-metadata booleans before fetching, and return RFC 9457 `error` objects on failure.
4. Honor `localResolutionOnly` and the fetch rules so a warm `FileMicroledgerStore` issues a range GET or no GET, matching `vdrRequestCount`.

Re-check with:

```bash
cd interop
./run.sh scenarios --resolver zkred
```
