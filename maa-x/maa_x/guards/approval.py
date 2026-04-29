"""Approval guard — raises ApprovalRequiredError when risk threshold is exceeded."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Mapping

from ..exceptions import ApprovalRequiredError
from ..persistence.base import ApprovalRecord, PersistenceBackend


@dataclass(slots=True)
class ApprovalRequest:
    tenant_id: str
    action: str
    risk_score: float
    reason: str
    requested_by: str = "unknown"
    action_hash: str | None = None

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

    def assess(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        flags = self._flags(state, config)
        risk_score = float(
            config.get("risk_score", state.get("risk_score", self._default_risk(flags)))
        )
        action = str(config.get("action", state.get("action", "governed_invoke")))
        tenant_id = str(config.get("tenant_id", state.get("tenant_id", "default")))
        requested_by = str(
            config.get("operator_id", state.get("operator_id", state.get("governance", {}).get("tenant", {}).get("operator_id", "unknown")))
        )
        reason = str(config.get("approval_reason", f"Approval required for {action}"))
        request = ApprovalRequest(
            tenant_id=tenant_id,
            action=action,
            risk_score=risk_score,
            reason=reason,
            requested_by=requested_by,
            action_hash=config.get("action_hash") or state.get("action_hash") or self._derive_action_hash(tenant_id, action, requested_by),
        )
        needs_approval = risk_score >= self.risk_threshold or bool(flags & self.require_approval_for)
        approved = False
        approval_id = config.get("approval_id") or state.get("approval_id")
        if approval_id and self.persistence:
            record = self.persistence.get_approval(str(approval_id))
            approved = bool(record and record.approved and record.action_hash == request.resolved_hash())
        return {
            "needs_approval": needs_approval,
            "approved": approved,
            "risk_score": risk_score,
            "flags": sorted(flags),
            "approval_id": approval_id if approved else None,
            "interrupt_supported": self.allow_interrupt_handoff,
            "request": request,
        }

    def create_request(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> ApprovalRecord:
        if not self.persistence:
            raise ApprovalRequiredError("Approval persistence backend is required to create approval requests")
        result = self.assess(state, config)
        request: ApprovalRequest = result["request"]
        return self.persistence.create_approval(
            tenant_id=request.tenant_id,
            action=request.action,
            action_hash=request.resolved_hash(),
            requested_by=request.requested_by,
            reason=request.reason,
            risk_score=request.risk_score,
        )

    def enforce(
        self,
        state: Mapping[str, Any] | None,
        config: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.assess(state, config)
        if result["needs_approval"] and not result["approved"]:
            approval_record = self.create_request(state, config) if self.persistence else None
            raise ApprovalRequiredError(
                "Approval required before governed invoke"
                + (f". approval_id={approval_record.approval_id}" if approval_record else "")
            )
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
    def _derive_action_hash(tenant_id: str, action: str, requested_by: str) -> str:
        raw = f"{tenant_id}:{action}:{requested_by}".encode()
        return sha256(raw).hexdigest()

    @staticmethod
    def _default_risk(flags: set[str]) -> float:
        if "high_risk" in flags:
            return 0.95
        if "external_api_call" in flags:
            return 0.75
        return 0.0