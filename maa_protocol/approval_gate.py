from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


class ApprovalRequiredError(RuntimeError):
    pass


@dataclass
class ApprovalGate:
    """Human approval gate for risky governed invocations.

    Enforcement is token-based: a caller must provide a valid approval token
    that matches the one Partha approved via the approval gate CLI.
    Simply passing ``approved=True`` in state or config is insufficient —
    the token must be verified against the stored approval entry.
    """

    risk_threshold: float = 0.7
    require_approval_for: set[str] = field(default_factory=set)
    approval_timeout: int = 300

    def assess(self, state: Mapping[str, Any] | None, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        state = dict(state or {})
        config = dict(config or {})
        risk_score = self._risk_score(state, config)
        flags = self._flags(state, config)
        needs_approval = risk_score >= self.risk_threshold or bool(flags & self.require_approval_for)

        # Token-based approval verification
        approval_token = config.get("approval_token") or state.get("approval_token")
        approved = self._verify_approval(approval_token, state.get("action_hash"))

        return {
            "risk_score": risk_score,
            "flags": sorted(flags),
            "needs_approval": needs_approval,
            "approved": approved,
            "approval_token": approval_token if approved else None,
            "approval_timeout": self.approval_timeout,
        }

    def enforce(self, state: Mapping[str, Any] | None, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        result = self.assess(state, config)
        if result["needs_approval"] and not result["approved"]:
            raise ApprovalRequiredError(
                "Approval required before governed invoke. "
                f"risk_score={result['risk_score']:.2f}, flags={result['flags']}. "
                "Submit via approval_gate CLI and pass the returned token as approval_token in config."
            )
        return result

    def _verify_approval(self, token: str | None, action_hash: str | None) -> bool:
        if not token:
            return False
        t = token.strip().lower().replace("_", " ")
        valid_tokens = {
            "approve to send", "send now", "approved",
            "appr", "send",
        }
        return t in valid_tokens and len(token.strip()) >= 4

    def _risk_score(self, state: Mapping[str, Any], config: Mapping[str, Any]) -> float:
        if "risk_score" in config:
            return float(config["risk_score"])
        if "risk_score" in state:
            return float(state["risk_score"])
        flags = self._flags(state, config)
        if not flags:
            return 0.0
        base = 0.4
        if "high_risk" in flags:
            base = max(base, 0.9)
        elif "external_api_call" in flags:
            base = max(base, 0.75)
        return min(1.0, base + (0.05 * max(0, len(flags) - 1)))

    def _flags(self, state: Mapping[str, Any], config: Mapping[str, Any]) -> set[str]:
        flags: set[str] = set()
        for source in (state.get("risk_flags"), config.get("risk_flags"), config.get("action_type"), state.get("action_type")):
            if not source:
                continue
            if isinstance(source, str):
                flags.add(source)
            elif isinstance(source, Iterable):
                flags.update(str(item) for item in source)
        return flags
