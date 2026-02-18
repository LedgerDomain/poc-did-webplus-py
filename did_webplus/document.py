"""DID document model and validation for did:webplus."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DIDDocument(BaseModel):
    """
    did:webplus DID document model.

    Conforms to DID Core with did:webplus-specific fields.
    """

    id: str = Field(..., description="The DID (id field per DID spec)")
    selfHash: str = Field(..., alias="selfHash")
    prevDIDDocumentSelfHash: str | None = Field(None, alias="prevDIDDocumentSelfHash")
    updateRules: dict[str, Any] = Field(..., alias="updateRules")
    proofs: list[str] = Field(default_factory=list, alias="proofs")
    validFrom: str = Field(..., alias="validFrom")
    versionId: int = Field(..., alias="versionId", ge=0)
    verificationMethod: list[dict[str, Any]] = Field(
        default_factory=list, alias="verificationMethod"
    )
    authentication: list[str] = Field(default_factory=list, alias="authentication")
    assertionMethod: list[str] = Field(default_factory=list, alias="assertionMethod")
    keyAgreement: list[str] = Field(default_factory=list, alias="keyAgreement")
    capabilityInvocation: list[str] = Field(
        default_factory=list, alias="capabilityInvocation"
    )
    capabilityDelegation: list[str] = Field(
        default_factory=list, alias="capabilityDelegation"
    )

    model_config = {"populate_by_name": True}

    @property
    def did(self) -> str:
        return self.id

    @property
    def self_hash(self) -> str:
        return self.selfHash

    @property
    def prev_did_document_self_hash(self) -> str | None:
        return self.prevDIDDocumentSelfHash

    @property
    def valid_from(self) -> str:
        return self.validFrom

    @property
    def version_id(self) -> int:
        return self.versionId

    def is_root_document(self) -> bool:
        return self.prevDIDDocumentSelfHash is None

    def is_deactivated(self) -> bool:
        """True if updateRules is empty (tombstoned)."""
        return self.updateRules == {}

    def verify_chain_constraints(
        self, prev_document: DIDDocument | None
    ) -> None:
        """
        Verify chain constraints (prev hash, versionId, validFrom).

        Raises:
            ValueError: If constraints are violated.
        """
        if self.is_root_document():
            if prev_document is not None:
                raise ValueError(
                    "Root DID document cannot have a previous document"
                )
            if self.versionId != 0:
                raise ValueError(
                    f"Root DID document must have versionId 0, got {self.versionId}"
                )
        else:
            if prev_document is None:
                raise ValueError(
                    "Non-root DID document must have a previous document"
                )
            if self.prevDIDDocumentSelfHash != prev_document.selfHash:
                raise ValueError(
                    f"prevDIDDocumentSelfHash {self.prevDIDDocumentSelfHash!r} "
                    f"does not match previous document's selfHash "
                    f"{prev_document.selfHash!r}"
                )
            if self.versionId != prev_document.versionId + 1:
                raise ValueError(
                    f"versionId must be prev.versionId + 1: "
                    f"expected {prev_document.versionId + 1}, got {self.versionId}"
                )
            prev_valid = _parse_rfc3339(prev_document.validFrom)
            curr_valid = _parse_rfc3339(self.validFrom)
            if curr_valid <= prev_valid:
                raise ValueError(
                    f"validFrom must be > previous: "
                    f"{self.validFrom} <= {prev_document.validFrom}"
                )

        valid_dt = _parse_rfc3339(self.validFrom)
        if valid_dt.timestamp() < 0:
            raise ValueError(
                f"validFrom must not be before UNIX epoch: {self.validFrom}"
            )
        if valid_dt.microsecond % 1000 != 0:
            raise ValueError(
                f"validFrom must have millisecond precision or less: {self.validFrom}"
            )


def _parse_rfc3339(s: str) -> datetime:
    """Parse RFC 3339 timestamp (with optional Z or offset)."""
    from datetime import timezone

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_did_document(jcs_str: str) -> DIDDocument:
    """Parse a JCS-serialized DID document."""
    import json

    data = json.loads(jcs_str)
    return DIDDocument.model_validate(data)
