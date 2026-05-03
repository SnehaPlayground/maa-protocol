"""Approval guard for risk-gated governance actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..exceptions import ApprovalPersistenceError, ApprovalRequiredError
from ..persistence.base import ApprovalRecord, PersistenceBackend


class ApprovalRequest(BaseModel):
    """Validated approval request payload."""

    model_config = ConfigDict(frozen=True)

    tenant_id: str
    action: str
    risk_score: float = Field(ge=0.0, le=1.0)
    reason: str
    requested_by: str
    action_hash: str | None = None

    @field_validator("tenant_id", "action", "reason", "requested_by")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    def resolved_hash(self) -> str:
        if self.action_hash:
            return self.action_hash
        raw = f"{self.tenant_id}:{self.action}:{self.requested_by}".encode()
        return sha256(raw).hexdigest()


@dataclass(slots=True)
class ApprovalGate:
    risk_threshold: float = 0.7
    persistence: PersistenceBackend | None = None
    require_approval_for: set[str] = field(default_factory=set)
    allow_interrupt_handoff: bool = True

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.risk_threshold) <= 1.0:
            raise ValueError("risk_threshold must be in [0.0, 1.0]")

    def assess(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        current_state = dict(state or {})
        payload = dict(config or {})
        flags = self._flags(current_state, payload)
        risk_score = float(
            payload.get(
                "risk_score",
                current_state.get("risk_score", self._default_risk(flags)),
            )
        )
        action = str(payload.get("action", current_state.get("action", "governed_invoke")))
        tenant_id = str(payload.get("tenant_id", current_state.get("tenant_id", ""))).strip()
        requested_by = str(payload.get("operator_id", current_state.get("operator_id", "unknown")))
        reason = str(payload.get("approval_reason", f"Approval required for {action}"))
        if not tenant_id:
            raise ValueError("Approval assessment requires tenant_id")

        request = ApprovalRequest.model_validate(
            {
                "tenant_id": tenant_id,
                "action": action,
                "risk_score": risk_score,
                "reason": reason,
                "requested_by": requested_by,
                "action_hash": payload.get("action_hash") or current_state.get("action_hash"),
            }
        )
        approval_id = payload.get("approval_id") or current_state.get("approval_id")
        approved = False
        if approval_id and self.persistence:
            record = self.persistence.get_approval(
                str(approval_id),
                caller_tenant_id=request.tenant_id,
            )
            approved = bool(
                record
                and record.approved
                and record.action_hash == request.resolved_hash()
            )

        needs_approval = (
            request.risk_score >= self.risk_threshold
            or bool(flags & self.require_approval_for)
        )
        return {
            "needs_approval": needs_approval,
            "approved": approved,
            "risk_score": request.risk_score,
            "flags": sorted(flags),
            "approval_id": str(approval_id) if approved and approval_id else None,
            "interrupt_supported": self.allow_interrupt_handoff,
            "request": request,
        }

    def create_request(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> ApprovalRecord:
        if self.persistence is None:
            raise ApprovalPersistenceError(
                "Approval persistence backend is required to create approval requests"
            )
        result = self.assess(state, config)
        request: ApprovalRequest = result["request"]
        return self.persistence.create_approval(
            tenant_id=request.tenant_id,
            action=request.action,
            action_hash=request.resolved_hash(),
            requested_by=request.requested_by,
            reason=request.reason,
            risk_score=request.risk_score,
            caller_tenant_id=request.tenant_id,
        )

    def enforce(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.assess(state, config)
        if result["needs_approval"] and not result["approved"]:
            approval_record = self.create_request(state, config) if self.persistence else None
            suffix = f". approval_id={approval_record.approval_id}" if approval_record else ""
            raise ApprovalRequiredError(f"Approval required before governed invoke{suffix}")
        return {
            "needs_approval": result["needs_approval"],
            "approved": result["approved"],
            "risk_score": result["risk_score"],
            "flags": result["flags"],
            "approval_id": result["approval_id"],
        }

    @staticmethod
    def _flags(state: Mapping[str, Any], config: Mapping[str, Any]) -> set[str]:
        values: set[str] = set()
        for key in ("risk_flags", "action_type"):
            for source in (state.get(key), config.get(key)):
                if not source:
                    continue
                if isinstance(source, str):
                    values.add(source)
                else:
                    values.update(str(item) for item in source)
        return values

    @staticmethod
    def _default_risk(flags: set[str]) -> float:
        if "high_risk" in flags:
            return 0.95
        if "external_api_call" in flags:
            return 0.75
        return 0.0
