"""Resolution options, RFC 9457 errors, locality plan, and metadata builders."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# RFC 9457 / W3C DID + did:webplus error type URIs
# ---------------------------------------------------------------------------

_W3C_DID_NS = "https://www.w3.org/ns/did#"
_WEBPLUS_SPEC = "https://ledgerdomain.github.io/did-webplus-spec#"

INVALID_DID = f"{_W3C_DID_NS}INVALID_DID"
INVALID_DID_URL = f"{_W3C_DID_NS}INVALID_DID_URL"
INVALID_OPTIONS = f"{_W3C_DID_NS}INVALID_OPTIONS"
NOT_FOUND = f"{_W3C_DID_NS}NOT_FOUND"
INVALID_DID_DOCUMENT = f"{_W3C_DID_NS}INVALID_DID_DOCUMENT"
INTERNAL_ERROR = f"{_W3C_DID_NS}INTERNAL_ERROR"
LOCAL_RESOLUTION_NOT_POSSIBLE = f"{_WEBPLUS_SPEC}LOCAL_RESOLUTION_NOT_POSSIBLE"
VDR_FETCH_FAILED = f"{_WEBPLUS_SPEC}VDR_FETCH_FAILED"

_ERROR_TITLES: dict[str, str] = {
    INVALID_DID: "Invalid DID",
    INVALID_DID_URL: "Invalid DID URL",
    INVALID_OPTIONS: "Invalid Options",
    NOT_FOUND: "Not Found",
    INVALID_DID_DOCUMENT: "Invalid DID Document",
    INTERNAL_ERROR: "Internal Error",
    LOCAL_RESOLUTION_NOT_POSSIBLE: "Local Resolution Not Possible",
    VDR_FETCH_FAILED: "VDR Fetch Failed",
}

CONTENT_TYPE_DID_JSON = "application/did+json"


@dataclass(frozen=True)
class ResolutionOptions:
    """Caller-selected DID resolution options (did:webplus-specific)."""

    request_create: bool = False
    request_next: bool = False
    request_latest: bool = False
    request_deactivated: bool = False
    local_resolution_only: bool = False

    @classmethod
    def from_wire(cls, wire: dict[str, Any] | None) -> ResolutionOptions:
        """Build options from camelCase wire keys."""
        if not wire:
            return cls()
        return cls(
            request_create=bool(wire.get("requestCreate")),
            request_next=bool(wire.get("requestNext")),
            request_latest=bool(wire.get("requestLatest")),
            request_deactivated=bool(wire.get("requestDeactivated")),
            local_resolution_only=bool(wire.get("localResolutionOnly")),
        )

    @classmethod
    def coalesce(
        cls,
        options: ResolutionOptions | None = None,
        *,
        no_fetch: bool = False,
    ) -> ResolutionOptions:
        """
        Merge explicit options with the ``no_fetch`` compatibility alias.

        ``no_fetch=True`` is treated as ``localResolutionOnly=True``.
        """
        base = options if options is not None else cls()
        if no_fetch and not base.local_resolution_only:
            return replace(base, local_resolution_only=True)
        return base

    def to_wire(self) -> dict[str, bool]:
        """CamelCase wire representation of all option fields."""
        return {
            "requestCreate": self.request_create,
            "requestNext": self.request_next,
            "requestLatest": self.request_latest,
            "requestDeactivated": self.request_deactivated,
            "localResolutionOnly": self.local_resolution_only,
        }


@dataclass(frozen=True)
class LocalDocumentRef:
    """Minimal view of one document in a contiguous verified local prefix."""

    version_id: int
    self_hash: str
    deactivated: bool


@dataclass(frozen=True)
class LocalPrefixSnapshot:
    """
    Contiguous verified local prefix for one DID, ordered by ``versionId``.

    The planner inspects only this snapshot; it does not perform I/O.
    """

    documents: tuple[LocalDocumentRef, ...] = ()

    @classmethod
    def from_documents(
        cls, documents: list[LocalDocumentRef] | tuple[LocalDocumentRef, ...]
    ) -> LocalPrefixSnapshot:
        """Build a snapshot sorted by ``version_id`` (must be contiguous from 0)."""
        ordered = tuple(sorted(documents, key=lambda d: d.version_id))
        return cls(documents=ordered)

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def is_empty(self) -> bool:
        return not self.documents

    @property
    def latest(self) -> LocalDocumentRef | None:
        return self.documents[-1] if self.documents else None

    @property
    def tip_is_deactivated(self) -> bool:
        tip = self.latest
        return tip is not None and tip.deactivated

    def get_by_version_id(self, version_id: int) -> LocalDocumentRef | None:
        for doc in self.documents:
            if doc.version_id == version_id:
                return doc
        return None

    def get_by_self_hash(self, self_hash: str) -> LocalDocumentRef | None:
        for doc in self.documents:
            if doc.self_hash == self_hash:
                return doc
        return None

    def has_version_0(self) -> bool:
        return self.get_by_version_id(0) is not None


@dataclass(frozen=True)
class LocalityPlan:
    """
    Pre-fetch locality determination for one resolution attempt.

    The three resolution booleans are frozen before any VDR/VDG fetch and MUST
    NOT be revised after data arrives.
    """

    requested_document_local: bool
    """Whether the requested document was already in the local verified prefix."""

    creation_metadata_local: bool
    """Whether creation metadata is locally satisfiable (vacuous if not requested)."""

    next_metadata_local: bool
    """Whether next-update metadata is locally determined (vacuous if not requested)."""

    latest_or_deactivated_metadata_local: bool
    """Whether latest/deactivated metadata is locally satisfiable (vacuous if not requested)."""

    should_fetch: bool
    """Whether this resolution will attempt a VDR/VDG fetch."""

    did_document_resolved_locally: bool
    did_document_metadata_resolved_locally: bool
    fetched_updates_from_vdr: bool

    early_failure: ProblemDetails | None = None
    """
    Pre-fetch terminal failure, if any (conflict, known absence, or
    ``localResolutionOnly`` impossibility). When set, ``should_fetch`` is
    ``false`` and no VDR/VDG request MUST be made.
    """


@dataclass(frozen=True)
class ProblemDetails:
    """RFC 9457 problem details object carried in DID Resolution Metadata."""

    type: str
    title: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "title": self.title,
            "detail": self.detail,
        }

    @classmethod
    def make(
        cls,
        type_uri: str,
        detail: str,
        *,
        title: str | None = None,
    ) -> ProblemDetails:
        """Build problem details with the canonical title for ``type_uri``."""
        resolved_title = title if title is not None else _ERROR_TITLES.get(
            type_uri, "Error"
        )
        return cls(type=type_uri, title=resolved_title, detail=detail)


# ---------------------------------------------------------------------------
# Pre-fetch locality planner
# ---------------------------------------------------------------------------


def _query_conflict(
    snapshot: LocalPrefixSnapshot,
    query_self_hash: str | None,
    query_version_id: int | None,
) -> bool:
    """
    True when both query params are present and either identifies a local
    document that the other disagrees with.
    """
    if query_self_hash is None or query_version_id is None:
        return False
    by_hash = snapshot.get_by_self_hash(query_self_hash)
    by_version = snapshot.get_by_version_id(query_version_id)
    if by_hash is not None and by_hash.version_id != query_version_id:
        return True
    if by_version is not None and by_version.self_hash != query_self_hash:
        return True
    return False


def _known_absence(
    snapshot: LocalPrefixSnapshot,
    query_self_hash: str | None,
    query_version_id: int | None,
) -> bool:
    """
    True when a deactivated local tip proves the addressed document cannot exist.

    A known deactivation proves the true latest document, no successor, and
    absence of unknown hashes or later versions.
    """
    if query_self_hash is None and query_version_id is None:
        return False
    tip = snapshot.latest
    if tip is None or not tip.deactivated:
        return False
    if query_version_id is not None and query_version_id > tip.version_id:
        return True
    if query_self_hash is not None and snapshot.get_by_self_hash(query_self_hash) is None:
        return True
    if (
        query_version_id is not None
        and snapshot.get_by_version_id(query_version_id) is None
        and query_version_id <= tip.version_id
    ):
        # Contiguous prefix: versions within [0, tip] must be present; if missing,
        # treat as not present (should not occur for a verified contiguous prefix).
        return True
    return False


def _lookup_addressed_document(
    snapshot: LocalPrefixSnapshot,
    query_self_hash: str | None,
    query_version_id: int | None,
) -> LocalDocumentRef | None:
    """Return the locally-known document addressed by query params, if any."""
    if query_self_hash is not None:
        return snapshot.get_by_self_hash(query_self_hash)
    if query_version_id is not None:
        return snapshot.get_by_version_id(query_version_id)
    return None


def _creation_metadata_local(
    snapshot: LocalPrefixSnapshot,
    *,
    requested: bool,
) -> bool:
    """Creation metadata is local iff version 0 is present (vacuous if unrequested)."""
    if not requested:
        return True
    return snapshot.has_version_0()


def _next_metadata_local(
    snapshot: LocalPrefixSnapshot,
    requested_doc: LocalDocumentRef | None,
    *,
    document_local: bool,
    requested: bool,
) -> bool:
    """
    Next metadata is local iff the successor is present or the requested
    document is deactivated. A non-deactivated local tip requires a fetch to
    establish absence. If the document itself is not local, next is not local.
    """
    if not requested:
        return True
    if not document_local or requested_doc is None:
        return False
    if requested_doc.deactivated:
        return True
    successor = snapshot.get_by_version_id(requested_doc.version_id + 1)
    return successor is not None


def _latest_or_deactivated_metadata_local(
    snapshot: LocalPrefixSnapshot,
    *,
    requested: bool,
) -> bool:
    """
    Latest/deactivated metadata is local iff the latest-known local document
    is deactivated (vacuous if unrequested).
    """
    if not requested:
        return True
    return snapshot.tip_is_deactivated


def plan_locality(
    snapshot: LocalPrefixSnapshot,
    *,
    query_self_hash: str | None = None,
    query_version_id: int | None = None,
    options: ResolutionOptions | None = None,
) -> LocalityPlan:
    """
    Freeze document/metadata locality and the fetch decision before any VDR/VDG
    request.

    Inspects only the contiguous verified local prefix. Sets ``early_failure``
    for locally detectable query conflicts (``INVALID_DID_URL``), known absence
    after deactivation (``NOT_FOUND``), and ``localResolutionOnly`` when any
    needed determination is not local (``LOCAL_RESOLUTION_NOT_POSSIBLE``).
    """
    opts = options if options is not None else ResolutionOptions()
    plain_did = query_self_hash is None and query_version_id is None

    # --- Locally detectable conflict: fail without fetching ---
    if _query_conflict(snapshot, query_self_hash, query_version_id):
        creation_local = _creation_metadata_local(
            snapshot, requested=opts.request_create
        )
        latest_local = _latest_or_deactivated_metadata_local(
            snapshot,
            requested=opts.request_latest or opts.request_deactivated,
        )
        # Document is not resolved locally on conflict; next depends on a
        # single requested document and is therefore not local.
        next_local = not opts.request_next
        metadata_local = creation_local and next_local and latest_local
        return LocalityPlan(
            requested_document_local=False,
            creation_metadata_local=creation_local,
            next_metadata_local=next_local,
            latest_or_deactivated_metadata_local=latest_local,
            should_fetch=False,
            did_document_resolved_locally=False,
            did_document_metadata_resolved_locally=metadata_local,
            fetched_updates_from_vdr=False,
            early_failure=ProblemDetails.make(
                INVALID_DID_URL,
                "selfHash and versionId query parameters conflict",
            ),
        )

    # --- Known absence after deactivation: NOT_FOUND without fetching ---
    if _known_absence(snapshot, query_self_hash, query_version_id):
        creation_local = _creation_metadata_local(
            snapshot, requested=opts.request_create
        )
        next_local = not opts.request_next
        latest_local = _latest_or_deactivated_metadata_local(
            snapshot,
            requested=opts.request_latest or opts.request_deactivated,
        )
        metadata_local = creation_local and next_local and latest_local
        return LocalityPlan(
            requested_document_local=False,
            creation_metadata_local=creation_local,
            next_metadata_local=next_local,
            latest_or_deactivated_metadata_local=latest_local,
            should_fetch=False,
            did_document_resolved_locally=False,
            did_document_metadata_resolved_locally=metadata_local,
            fetched_updates_from_vdr=False,
            early_failure=ProblemDetails.make(
                NOT_FOUND,
                "requested DID document is known absent after local deactivation",
            ),
        )

    # --- Requested-document locality ---
    requested_doc: LocalDocumentRef | None = None
    if plain_did:
        tip = snapshot.latest
        # Plain DID requires a fetch even when warm, unless tip is deactivated.
        if tip is not None and tip.deactivated:
            requested_doc = tip
            document_local = True
        else:
            document_local = False
    else:
        requested_doc = _lookup_addressed_document(
            snapshot, query_self_hash, query_version_id
        )
        document_local = requested_doc is not None

    creation_local = _creation_metadata_local(
        snapshot, requested=opts.request_create
    )
    next_local = _next_metadata_local(
        snapshot,
        requested_doc,
        document_local=document_local,
        requested=opts.request_next,
    )
    latest_local = _latest_or_deactivated_metadata_local(
        snapshot,
        requested=opts.request_latest or opts.request_deactivated,
    )
    metadata_local = creation_local and next_local and latest_local

    needs_network = not document_local or not metadata_local

    if opts.local_resolution_only:
        early: ProblemDetails | None = None
        if needs_network:
            early = ProblemDetails.make(
                LOCAL_RESOLUTION_NOT_POSSIBLE,
                "local-only resolution cannot satisfy document or metadata",
            )
        return LocalityPlan(
            requested_document_local=document_local,
            creation_metadata_local=creation_local,
            next_metadata_local=next_local,
            latest_or_deactivated_metadata_local=latest_local,
            should_fetch=False,
            did_document_resolved_locally=document_local,
            did_document_metadata_resolved_locally=metadata_local,
            fetched_updates_from_vdr=False,
            early_failure=early,
        )

    should_fetch = needs_network
    return LocalityPlan(
        requested_document_local=document_local,
        creation_metadata_local=creation_local,
        next_metadata_local=next_local,
        latest_or_deactivated_metadata_local=latest_local,
        should_fetch=should_fetch,
        did_document_resolved_locally=document_local,
        did_document_metadata_resolved_locally=metadata_local,
        fetched_updates_from_vdr=should_fetch,
        early_failure=None,
    )


# ---------------------------------------------------------------------------
# UTC timestamp helpers
# ---------------------------------------------------------------------------


def _parse_utc_timestamp(ts: str) -> datetime:
    """Parse an RFC 3339 / ISO-8601 UTC timestamp into an aware datetime."""
    raw = ts.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def normalize_timestamp_milliseconds(ts: str) -> str:
    """
    Normalize a UTC timestamp to at most millisecond precision.

    Output uses upper-case ``T``/``Z``. Fractional seconds are floored to
    milliseconds and trailing zeros in the fractional part are preserved only
    for the significant digit groups present after flooring (0, 1, 2, or 3 digits).
    When the floored fractional part is zero, the fractional component is omitted.
    """
    dt = _parse_utc_timestamp(ts)
    # Floor to whole milliseconds (drop microseconds beyond ms).
    ms = dt.microsecond // 1000
    base = dt.strftime("%Y-%m-%dT%H:%M:%S")
    if ms == 0:
        return f"{base}Z"
    # Emit 1–3 fractional digits without trailing zeros beyond significance,
    # but always enough digits to represent the millisecond value exactly.
    frac = f"{ms:03d}".rstrip("0")
    return f"{base}.{frac}Z"


def floor_timestamp_seconds(ts: str) -> str:
    """
    Floor a UTC timestamp to whole seconds as ``YYYY-MM-DDTHH:MM:SSZ``.
    """
    dt = _parse_utc_timestamp(ts)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def timestamp_pair(ts: str) -> tuple[str, str]:
    """Return ``(seconds_floor, milliseconds_normalized)`` for ``ts``."""
    ms = normalize_timestamp_milliseconds(ts)
    return floor_timestamp_seconds(ms), ms


# ---------------------------------------------------------------------------
# Exact wire metadata builders
# ---------------------------------------------------------------------------


def build_did_document_metadata(
    *,
    options: ResolutionOptions,
    version_id: int,
    valid_from: str,
    is_root: bool,
    root_valid_from: str | None = None,
    next_valid_from: str | None = None,
    next_version_id: int | None = None,
    latest_valid_from: str | None = None,
    latest_version_id: int | None = None,
    deactivated: bool = False,
) -> dict[str, Any]:
    """
    Build the exact DID Document Metadata wire dictionary.

    Presence rules follow the did:webplus spec:
    - ``versionId`` always (ASCII string);
    - ``updated`` / ``updatedMilliseconds`` only for non-root documents;
    - creation / next / latest groups only when requested (and values exist);
    - ``deactivated: true`` whenever known; ``false`` only when requested.
    """
    meta: dict[str, Any] = {
        "versionId": str(version_id),
    }

    if not is_root:
        updated, updated_ms = timestamp_pair(valid_from)
        meta["updated"] = updated
        meta["updatedMilliseconds"] = updated_ms

    if options.request_create:
        if root_valid_from is None:
            raise ValueError(
                "root_valid_from is required when requestCreate is set"
            )
        created, created_ms = timestamp_pair(root_valid_from)
        meta["created"] = created
        meta["createdMilliseconds"] = created_ms

    if options.request_next and next_valid_from is not None and next_version_id is not None:
        next_update, next_update_ms = timestamp_pair(next_valid_from)
        meta["nextUpdate"] = next_update
        meta["nextUpdateMilliseconds"] = next_update_ms
        meta["nextVersionId"] = str(next_version_id)

    if options.request_latest:
        if latest_valid_from is None or latest_version_id is None:
            raise ValueError(
                "latest_valid_from and latest_version_id are required "
                "when requestLatest is set"
            )
        latest_update, latest_update_ms = timestamp_pair(latest_valid_from)
        meta["latestUpdate"] = latest_update
        meta["latestUpdateMilliseconds"] = latest_update_ms
        meta["latestVersionId"] = str(latest_version_id)

    if deactivated:
        meta["deactivated"] = True
    elif options.request_deactivated:
        meta["deactivated"] = False

    return meta


def build_did_resolution_metadata(
    *,
    did_document_resolved_locally: bool,
    did_document_metadata_resolved_locally: bool,
    fetched_updates_from_vdr: bool,
    error: ProblemDetails | None = None,
    include_content_type: bool = True,
) -> dict[str, Any]:
    """
    Build DID Resolution Metadata wire dictionary.

    On success, ``contentType`` is ``application/did+json`` when
    ``include_content_type`` is true (resolveRepresentation). On failure,
    ``error`` is an RFC 9457 object and ``contentType`` is omitted.
    """
    meta: dict[str, Any] = {}
    if error is None and include_content_type:
        meta["contentType"] = CONTENT_TYPE_DID_JSON
    if error is not None:
        meta["error"] = error.to_dict()
    meta["fetchedUpdatesFromVDR"] = fetched_updates_from_vdr
    meta["didDocumentResolvedLocally"] = did_document_resolved_locally
    meta["didDocumentMetadataResolvedLocally"] = (
        did_document_metadata_resolved_locally
    )
    return meta


def build_failure_resolution_dict(
    error: ProblemDetails,
    *,
    did_document_resolved_locally: bool = False,
    did_document_metadata_resolved_locally: bool = False,
    fetched_updates_from_vdr: bool = False,
) -> dict[str, Any]:
    """Full resolution result dict for a failed resolution."""
    return {
        "didResolutionMetadata": build_did_resolution_metadata(
            did_document_resolved_locally=did_document_resolved_locally,
            did_document_metadata_resolved_locally=did_document_metadata_resolved_locally,
            fetched_updates_from_vdr=fetched_updates_from_vdr,
            error=error,
            include_content_type=False,
        ),
        "didDocument": None,
        "didDocumentMetadata": {},
    }


def build_success_resolution_dict(
    *,
    did_document: str,
    did_document_metadata: dict[str, Any],
    did_document_resolved_locally: bool,
    did_document_metadata_resolved_locally: bool,
    fetched_updates_from_vdr: bool,
) -> dict[str, Any]:
    """Full resolution result dict for a successful representation resolve."""
    return {
        "didResolutionMetadata": build_did_resolution_metadata(
            did_document_resolved_locally=did_document_resolved_locally,
            did_document_metadata_resolved_locally=did_document_metadata_resolved_locally,
            fetched_updates_from_vdr=fetched_updates_from_vdr,
            error=None,
            include_content_type=True,
        ),
        "didDocument": did_document,
        "didDocumentMetadata": did_document_metadata,
    }
