"""did:webplus Python Full DID Resolver."""

from did_webplus.resolution import (
    INTERNAL_ERROR,
    INVALID_DID,
    INVALID_DID_DOCUMENT,
    INVALID_DID_URL,
    INVALID_OPTIONS,
    LOCAL_RESOLUTION_NOT_POSSIBLE,
    NOT_FOUND,
    VDR_FETCH_FAILED,
    LocalDocumentRef,
    LocalityPlan,
    LocalPrefixSnapshot,
    ProblemDetails,
    ResolutionOptions,
    plan_locality,
)
from did_webplus.resolver import (
    FullDIDResolver,
    ResolutionError,
    ResolutionResult,
)
from did_webplus.store import SQLiteDIDDocStore

__all__ = [
    "INTERNAL_ERROR",
    "INVALID_DID",
    "INVALID_DID_DOCUMENT",
    "INVALID_DID_URL",
    "INVALID_OPTIONS",
    "LOCAL_RESOLUTION_NOT_POSSIBLE",
    "NOT_FOUND",
    "VDR_FETCH_FAILED",
    "FullDIDResolver",
    "LocalDocumentRef",
    "LocalityPlan",
    "LocalPrefixSnapshot",
    "ProblemDetails",
    "ResolutionError",
    "ResolutionOptions",
    "ResolutionResult",
    "SQLiteDIDDocStore",
    "plan_locality",
]
