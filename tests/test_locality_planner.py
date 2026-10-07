"""Table-driven unit tests for pre-fetch document and metadata locality rules."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from did_webplus.resolution import (
    INVALID_DID_URL,
    LOCAL_RESOLUTION_NOT_POSSIBLE,
    NOT_FOUND,
    LocalDocumentRef,
    LocalPrefixSnapshot,
    ResolutionOptions,
    plan_locality,
)


def _doc(version_id: int, self_hash: str, *, deactivated: bool = False) -> LocalDocumentRef:
    return LocalDocumentRef(
        version_id=version_id,
        self_hash=self_hash,
        deactivated=deactivated,
    )


def _prefix(*docs: LocalDocumentRef) -> LocalPrefixSnapshot:
    return LocalPrefixSnapshot.from_documents(docs)


# Contiguous active microledger tip at v2 (not deactivated).
WARM_ACTIVE = _prefix(
    _doc(0, "h0"),
    _doc(1, "h1"),
    _doc(2, "h2"),
)

# Contiguous microledger ending in a deactivation tombstone at v3.
WARM_DEACTIVATED = _prefix(
    _doc(0, "h0"),
    _doc(1, "h1"),
    _doc(2, "h2"),
    _doc(3, "h3", deactivated=True),
)

# Tip active but missing root (non-contiguous / partial — version 0 absent).
PARTIAL_NO_ROOT = _prefix(
    _doc(1, "h1"),
    _doc(2, "h2"),
)

COLD = _prefix()


@dataclass(frozen=True)
class Expect:
    document_local: bool
    metadata_local: bool
    should_fetch: bool
    early_type: str | None = None
    creation_local: bool | None = None
    next_local: bool | None = None
    latest_local: bool | None = None


def _assert_plan(
    snapshot: LocalPrefixSnapshot,
    expect: Expect,
    *,
    query_self_hash: str | None = None,
    query_version_id: int | None = None,
    options: ResolutionOptions | None = None,
) -> None:
    plan = plan_locality(
        snapshot,
        query_self_hash=query_self_hash,
        query_version_id=query_version_id,
        options=options,
    )
    assert plan.did_document_resolved_locally is expect.document_local
    assert plan.requested_document_local is expect.document_local
    assert plan.did_document_metadata_resolved_locally is expect.metadata_local
    assert plan.should_fetch is expect.should_fetch
    assert plan.fetched_updates_from_vdr is expect.should_fetch
    if expect.early_type is None:
        assert plan.early_failure is None
    else:
        assert plan.early_failure is not None
        assert plan.early_failure.type == expect.early_type
    if expect.creation_local is not None:
        assert plan.creation_metadata_local is expect.creation_local
    if expect.next_local is not None:
        assert plan.next_metadata_local is expect.next_local
    if expect.latest_local is not None:
        assert plan.latest_or_deactivated_metadata_local is expect.latest_local


# ---------------------------------------------------------------------------
# Plain DID
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,snapshot,options,expect",
    [
        (
            "cold-plain",
            COLD,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
        (
            "warm-plain-requires-fetch",
            WARM_ACTIVE,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
        (
            "warm-plain-deactivated-local",
            WARM_DEACTIVATED,
            ResolutionOptions(),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "warm-plain-deactivated-all-metadata-local",
            WARM_DEACTIVATED,
            ResolutionOptions(
                request_create=True,
                request_next=True,
                request_latest=True,
                request_deactivated=True,
            ),
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                creation_local=True,
                next_local=True,
                latest_local=True,
            ),
        ),
        (
            "warm-plain-request-latest-forces-fetch",
            WARM_ACTIVE,
            ResolutionOptions(request_latest=True),
            Expect(
                document_local=False,
                metadata_local=False,
                should_fetch=True,
                latest_local=False,
            ),
        ),
    ],
)
def test_plain_did_locality(
    name: str,
    snapshot: LocalPrefixSnapshot,
    options: ResolutionOptions,
    expect: Expect,
) -> None:
    _assert_plan(snapshot, expect, options=options)


# ---------------------------------------------------------------------------
# Hash / version / both query forms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,snapshot,self_hash,version_id,options,expect",
    [
        (
            "hash-local-no-metadata",
            WARM_ACTIVE,
            "h1",
            None,
            ResolutionOptions(),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "version-local-no-metadata",
            WARM_ACTIVE,
            None,
            1,
            ResolutionOptions(),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "both-agree-local",
            WARM_ACTIVE,
            "h1",
            1,
            ResolutionOptions(),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "hash-missing-fetch",
            WARM_ACTIVE,
            "h-missing",
            None,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
        (
            "version-missing-fetch",
            WARM_ACTIVE,
            None,
            9,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
        (
            "both-missing-fetch",
            WARM_ACTIVE,
            "h-missing",
            9,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
        (
            "cold-version-fetch",
            COLD,
            None,
            0,
            ResolutionOptions(),
            Expect(document_local=False, metadata_local=True, should_fetch=True),
        ),
    ],
)
def test_addressed_document_locality(
    name: str,
    snapshot: LocalPrefixSnapshot,
    self_hash: str | None,
    version_id: int | None,
    options: ResolutionOptions,
    expect: Expect,
) -> None:
    _assert_plan(
        snapshot,
        expect,
        query_self_hash=self_hash,
        query_version_id=version_id,
        options=options,
    )


# ---------------------------------------------------------------------------
# Conflicts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,self_hash,version_id",
    [
        ("hash-found-version-disagrees", "h1", 2),
        ("version-found-hash-disagrees", "h-wrong", 1),
        ("both-found-disagree", "h0", 1),
    ],
)
def test_query_conflict_no_fetch(
    name: str, self_hash: str, version_id: int
) -> None:
    _assert_plan(
        WARM_ACTIVE,
        Expect(
            document_local=False,
            metadata_local=True,
            should_fetch=False,
            early_type=INVALID_DID_URL,
        ),
        query_self_hash=self_hash,
        query_version_id=version_id,
    )


def test_query_conflict_preserves_metadata_split() -> None:
    _assert_plan(
        WARM_ACTIVE,
        Expect(
            document_local=False,
            metadata_local=False,
            should_fetch=False,
            early_type=INVALID_DID_URL,
            creation_local=True,
            next_local=False,
            latest_local=False,
        ),
        query_self_hash="h1",
        query_version_id=2,
        options=ResolutionOptions(request_create=True, request_next=True, request_latest=True),
    )


# ---------------------------------------------------------------------------
# Next-at-tip / local successor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,snapshot,self_hash,version_id,expect",
    [
        (
            "next-at-active-tip-forces-fetch",
            WARM_ACTIVE,
            "h2",
            2,
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=True,
                next_local=False,
            ),
        ),
        (
            "next-with-local-successor",
            WARM_ACTIVE,
            "h1",
            1,
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                next_local=True,
            ),
        ),
        (
            "next-on-deactivated-doc-local",
            WARM_DEACTIVATED,
            "h3",
            3,
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                next_local=True,
            ),
        ),
        (
            "next-on-non-tip-before-deactivation",
            WARM_DEACTIVATED,
            "h2",
            2,
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                next_local=True,
            ),
        ),
    ],
)
def test_next_metadata_locality(
    name: str,
    snapshot: LocalPrefixSnapshot,
    self_hash: str,
    version_id: int,
    expect: Expect,
) -> None:
    _assert_plan(
        snapshot,
        expect,
        query_self_hash=self_hash,
        query_version_id=version_id,
        options=ResolutionOptions(request_next=True),
    )


# ---------------------------------------------------------------------------
# Creation / latest / deactivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,snapshot,options,self_hash,version_id,expect",
    [
        (
            "creation-local-when-root-present",
            WARM_ACTIVE,
            ResolutionOptions(request_create=True),
            "h2",
            2,
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                creation_local=True,
            ),
        ),
        (
            "creation-not-local-without-root",
            PARTIAL_NO_ROOT,
            ResolutionOptions(request_create=True),
            "h2",
            2,
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=True,
                creation_local=False,
            ),
        ),
        (
            "latest-forces-fetch-when-tip-active",
            WARM_ACTIVE,
            ResolutionOptions(request_latest=True),
            "h1",
            1,
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=True,
                latest_local=False,
            ),
        ),
        (
            "deactivated-forces-fetch-when-tip-active",
            WARM_ACTIVE,
            ResolutionOptions(request_deactivated=True),
            "h1",
            1,
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=True,
                latest_local=False,
            ),
        ),
        (
            "latest-local-when-tip-deactivated",
            WARM_DEACTIVATED,
            ResolutionOptions(request_latest=True, request_deactivated=True),
            "h1",
            1,
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                latest_local=True,
            ),
        ),
        (
            "doc-local-metadata-forces-fetch",
            WARM_ACTIVE,
            ResolutionOptions(request_create=True, request_latest=True),
            "h1",
            1,
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=True,
                creation_local=True,
                latest_local=False,
            ),
        ),
    ],
)
def test_creation_latest_deactivated_locality(
    name: str,
    snapshot: LocalPrefixSnapshot,
    options: ResolutionOptions,
    self_hash: str,
    version_id: int,
    expect: Expect,
) -> None:
    _assert_plan(
        snapshot,
        expect,
        query_self_hash=self_hash,
        query_version_id=version_id,
        options=options,
    )


# ---------------------------------------------------------------------------
# Known absence after deactivation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,self_hash,version_id",
    [
        ("version-beyond-deactivated-tip", None, 4),
        ("unknown-hash-after-deactivation", "h-missing", None),
        ("both-absent-after-deactivation", "h-missing", 9),
    ],
)
def test_known_absence_no_fetch(
    name: str, self_hash: str | None, version_id: int | None
) -> None:
    _assert_plan(
        WARM_DEACTIVATED,
        Expect(
            document_local=False,
            metadata_local=True,
            should_fetch=False,
            early_type=NOT_FOUND,
        ),
        query_self_hash=self_hash,
        query_version_id=version_id,
    )


def test_known_absence_not_when_tip_active() -> None:
    _assert_plan(
        WARM_ACTIVE,
        Expect(document_local=False, metadata_local=True, should_fetch=True),
        query_version_id=9,
    )


# ---------------------------------------------------------------------------
# localResolutionOnly combinations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,snapshot,self_hash,version_id,options,expect",
    [
        (
            "local-only-success-addressed",
            WARM_ACTIVE,
            "h1",
            1,
            ResolutionOptions(local_resolution_only=True),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "local-only-success-plain-deactivated",
            WARM_DEACTIVATED,
            None,
            None,
            ResolutionOptions(
                local_resolution_only=True,
                request_create=True,
                request_next=True,
                request_latest=True,
                request_deactivated=True,
            ),
            Expect(document_local=True, metadata_local=True, should_fetch=False),
        ),
        (
            "local-only-fail-plain-active",
            WARM_ACTIVE,
            None,
            None,
            ResolutionOptions(local_resolution_only=True),
            Expect(
                document_local=False,
                metadata_local=True,
                should_fetch=False,
                early_type=LOCAL_RESOLUTION_NOT_POSSIBLE,
            ),
        ),
        (
            "local-only-fail-cold",
            COLD,
            None,
            0,
            ResolutionOptions(local_resolution_only=True),
            Expect(
                document_local=False,
                metadata_local=True,
                should_fetch=False,
                early_type=LOCAL_RESOLUTION_NOT_POSSIBLE,
            ),
        ),
        (
            "local-only-fail-next-at-tip",
            WARM_ACTIVE,
            "h2",
            2,
            ResolutionOptions(local_resolution_only=True, request_next=True),
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=False,
                early_type=LOCAL_RESOLUTION_NOT_POSSIBLE,
                next_local=False,
            ),
        ),
        (
            "local-only-fail-latest-active-tip",
            WARM_ACTIVE,
            "h1",
            1,
            ResolutionOptions(local_resolution_only=True, request_latest=True),
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=False,
                early_type=LOCAL_RESOLUTION_NOT_POSSIBLE,
                latest_local=False,
            ),
        ),
        (
            "local-only-fail-missing-creation",
            PARTIAL_NO_ROOT,
            "h2",
            2,
            ResolutionOptions(local_resolution_only=True, request_create=True),
            Expect(
                document_local=True,
                metadata_local=False,
                should_fetch=False,
                early_type=LOCAL_RESOLUTION_NOT_POSSIBLE,
                creation_local=False,
            ),
        ),
        (
            "local-only-success-next-with-successor",
            WARM_ACTIVE,
            "h0",
            0,
            ResolutionOptions(local_resolution_only=True, request_next=True, request_create=True),
            Expect(
                document_local=True,
                metadata_local=True,
                should_fetch=False,
                creation_local=True,
                next_local=True,
            ),
        ),
        (
            "local-only-known-absence-still-not-found",
            WARM_DEACTIVATED,
            None,
            99,
            ResolutionOptions(local_resolution_only=True),
            Expect(
                document_local=False,
                metadata_local=True,
                should_fetch=False,
                early_type=NOT_FOUND,
            ),
        ),
        (
            "local-only-conflict-still-invalid-did-url",
            WARM_ACTIVE,
            "h1",
            2,
            ResolutionOptions(local_resolution_only=True),
            Expect(
                document_local=False,
                metadata_local=True,
                should_fetch=False,
                early_type=INVALID_DID_URL,
            ),
        ),
    ],
)
def test_local_resolution_only_combinations(
    name: str,
    snapshot: LocalPrefixSnapshot,
    self_hash: str | None,
    version_id: int | None,
    options: ResolutionOptions,
    expect: Expect,
) -> None:
    _assert_plan(
        snapshot,
        expect,
        query_self_hash=self_hash,
        query_version_id=version_id,
        options=options,
    )


def test_vacuous_metadata_true_when_none_requested() -> None:
    plan = plan_locality(WARM_ACTIVE, query_self_hash="h1", query_version_id=1)
    assert plan.did_document_metadata_resolved_locally is True
    assert plan.creation_metadata_local is True
    assert plan.next_metadata_local is True
    assert plan.latest_or_deactivated_metadata_local is True
