from __future__ import annotations


class MaaProtocolError(Exception):
    """Base exception for Maa Protocol."""


class ApprovalRequiredError(MaaProtocolError):
    """Raised when a governed action requires approval before execution."""


class ApprovalPersistenceError(MaaProtocolError):
    """Raised when approval storage fails or is unavailable."""


class CostLimitExceededError(MaaProtocolError):
    """Raised when a hard cost limit is exceeded."""


class TenantAccessError(MaaProtocolError):
    """Raised when tenant or RBAC rules block an action."""


class CircuitOpenError(MaaProtocolError):
    """Raised when self-healing circuit breaker is open."""
