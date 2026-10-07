"""Unit tests for resolution options, timestamps, errors, and metadata builders."""

from __future__ import annotations

import pytest

from did_webplus.resolution import (
    INVALID_DID_URL,
    LOCAL_RESOLUTION_NOT_POSSIBLE,
    NOT_FOUND,
    VDR_FETCH_FAILED,
    ProblemDetails,
    ResolutionOptions,
    build_did_document_metadata,
    build_failure_resolution_dict,
    build_success_resolution_dict,
    floor_timestamp_seconds,
    normalize_timestamp_milliseconds,
    timestamp_pair,
)


def test_resolution_options_no_fetch_alias() -> None:
    opts = ResolutionOptions.coalesce(None, no_fetch=True)
    assert opts.local_resolution_only is True
    assert opts.request_create is False

    base = ResolutionOptions(request_create=True)
    merged = ResolutionOptions.coalesce(base, no_fetch=True)
    assert merged.request_create is True
    assert merged.local_resolution_only is True


def test_resolution_options_from_wire() -> None:
    opts = ResolutionOptions.from_wire(
        {
            "requestCreate": True,
            "requestNext": True,
            "requestLatest": False,
            "requestDeactivated": True,
            "localResolutionOnly": True,
        }
    )
    assert opts == ResolutionOptions(
        request_create=True,
        request_next=True,
        request_latest=False,
        request_deactivated=True,
        local_resolution_only=True,
    )


@pytest.mark.parametrize(
    "raw,expected_ms,expected_sec",
    [
        ("2025-01-01T00:00:03.875Z", "2025-01-01T00:00:03.875Z", "2025-01-01T00:00:03Z"),
        ("2025-01-01T00:00:00.001Z", "2025-01-01T00:00:00.001Z", "2025-01-01T00:00:00Z"),
        ("2020-12-20T19:18:50.8Z", "2020-12-20T19:18:50.8Z", "2020-12-20T19:18:50Z"),
        ("2020-12-20T20:13:27Z", "2020-12-20T20:13:27Z", "2020-12-20T20:13:27Z"),
        # Floor sub-millisecond precision
        ("2025-01-01T00:00:01.6339Z", "2025-01-01T00:00:01.633Z", "2025-01-01T00:00:01Z"),
        ("2024-01-01T00:00:00.000Z", "2024-01-01T00:00:00Z", "2024-01-01T00:00:00Z"),
    ],
)
def test_timestamp_normalization(
    raw: str, expected_ms: str, expected_sec: str
) -> None:
    assert normalize_timestamp_milliseconds(raw) == expected_ms
    assert floor_timestamp_seconds(raw) == expected_sec
    assert timestamp_pair(raw) == (expected_sec, expected_ms)


def test_metadata_root_no_options() -> None:
    meta = build_did_document_metadata(
        options=ResolutionOptions(),
        version_id=0,
        valid_from="2025-01-01T00:00:00.001Z",
        is_root=True,
        deactivated=False,
    )
    assert meta == {"versionId": "0"}


def test_metadata_non_root_default_options() -> None:
    meta = build_did_document_metadata(
        options=ResolutionOptions(),
        version_id=3,
        valid_from="2025-01-01T00:00:03.875Z",
        is_root=False,
        deactivated=False,
    )
    assert meta == {
        "versionId": "3",
        "updated": "2025-01-01T00:00:03Z",
        "updatedMilliseconds": "2025-01-01T00:00:03.875Z",
    }


def test_metadata_request_create_and_next() -> None:
    meta = build_did_document_metadata(
        options=ResolutionOptions(request_create=True, request_next=True),
        version_id=1,
        valid_from="2025-01-01T00:00:01.633Z",
        is_root=False,
        root_valid_from="2025-01-01T00:00:00.001Z",
        next_valid_from="2025-01-01T00:00:02.242Z",
        next_version_id=2,
    )
    assert meta == {
        "versionId": "1",
        "updated": "2025-01-01T00:00:01Z",
        "updatedMilliseconds": "2025-01-01T00:00:01.633Z",
        "created": "2025-01-01T00:00:00Z",
        "createdMilliseconds": "2025-01-01T00:00:00.001Z",
        "nextUpdate": "2025-01-01T00:00:02Z",
        "nextUpdateMilliseconds": "2025-01-01T00:00:02.242Z",
        "nextVersionId": "2",
    }


def test_metadata_next_omitted_when_no_successor() -> None:
    meta = build_did_document_metadata(
        options=ResolutionOptions(request_next=True),
        version_id=3,
        valid_from="2025-01-01T00:00:03.875Z",
        is_root=False,
        next_valid_from=None,
        next_version_id=None,
    )
    assert "nextUpdate" not in meta
    assert "nextVersionId" not in meta


def test_metadata_latest_and_deactivated_rules() -> None:
    known_deactivated = build_did_document_metadata(
        options=ResolutionOptions(),
        version_id=3,
        valid_from="2025-01-01T00:00:03.875Z",
        is_root=False,
        deactivated=True,
    )
    assert known_deactivated["deactivated"] is True

    requested_false = build_did_document_metadata(
        options=ResolutionOptions(request_deactivated=True),
        version_id=3,
        valid_from="2025-01-01T00:00:03.875Z",
        is_root=False,
        deactivated=False,
    )
    assert requested_false["deactivated"] is False

    omitted = build_did_document_metadata(
        options=ResolutionOptions(),
        version_id=3,
        valid_from="2025-01-01T00:00:03.875Z",
        is_root=False,
        deactivated=False,
    )
    assert "deactivated" not in omitted

    with_latest = build_did_document_metadata(
        options=ResolutionOptions(request_latest=True),
        version_id=1,
        valid_from="2025-01-01T00:00:01.633Z",
        is_root=False,
        latest_valid_from="2025-01-01T00:00:03.875Z",
        latest_version_id=3,
    )
    assert with_latest["latestUpdate"] == "2025-01-01T00:00:03Z"
    assert with_latest["latestUpdateMilliseconds"] == "2025-01-01T00:00:03.875Z"
    assert with_latest["latestVersionId"] == "3"


def test_failure_and_success_wire_shapes() -> None:
    problem = ProblemDetails.make(
        VDR_FETCH_FAILED,
        "VDR fetch failed for did:webplus:example.com:abc?versionId=1",
    )
    failed = build_failure_resolution_dict(
        problem,
        did_document_resolved_locally=True,
        did_document_metadata_resolved_locally=False,
        fetched_updates_from_vdr=True,
    )
    assert failed["didDocument"] is None
    assert failed["didDocumentMetadata"] == {}
    assert failed["didResolutionMetadata"] == {
        "error": {
            "type": VDR_FETCH_FAILED,
            "title": "VDR Fetch Failed",
            "detail": "VDR fetch failed for did:webplus:example.com:abc?versionId=1",
        },
        "fetchedUpdatesFromVDR": True,
        "didDocumentResolvedLocally": True,
        "didDocumentMetadataResolvedLocally": False,
    }
    assert "contentType" not in failed["didResolutionMetadata"]

    success = build_success_resolution_dict(
        did_document='{"id":"did:webplus:example.com:abc"}',
        did_document_metadata={"versionId": "0"},
        did_document_resolved_locally=False,
        did_document_metadata_resolved_locally=True,
        fetched_updates_from_vdr=True,
    )
    assert success["didDocument"] is not None
    assert success["didResolutionMetadata"]["contentType"] == "application/did+json"
    assert success["didResolutionMetadata"]["fetchedUpdatesFromVDR"] is True
    assert "error" not in success["didResolutionMetadata"]


def test_problem_details_titles() -> None:
    assert ProblemDetails.make(NOT_FOUND, "x").title == "Not Found"
    assert ProblemDetails.make(INVALID_DID_URL, "x").title == "Invalid DID URL"
    assert (
        ProblemDetails.make(LOCAL_RESOLUTION_NOT_POSSIBLE, "x").title
        == "Local Resolution Not Possible"
    )
