from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class AccessDeniedError(PermissionError):
    pass


@dataclass
class AccessControl:
    """Simple RBAC checks for LangGraph-facing governance wrapper."""

    role_permissions: dict[str, set[str]] = field(default_factory=lambda: {
        "admin": {"*"},
        "operator": {"invoke", "read", "approve"},
        "senior_analyst": {"invoke", "read"},
        "analyst": {"invoke", "read"},
        "viewer": {"read"},
    })
    default_action: str = "invoke"

    def check(self, user_role: str, action: str | None = None) -> None:
        action = action or self.default_action
        permissions = self.role_permissions.get(user_role, set())
        if "*" in permissions or action in permissions:
            return
        raise AccessDeniedError(f"Role '{user_role}' cannot perform '{action}'")

    def enforce(self, config: Mapping[str, Any] | None) -> dict[str, Any]:
        config = dict(config or {})
        role = str(config.get("user_role") or "operator")
        action = str(config.get("action") or self.default_action)
        self.check(role, action)
        return {"user_role": role, "action": action, "allowed": True}
