"""Custom exceptions for Maa-X."""


class MaaProtocolError(Exception):
    """Base exception for Maa-X errors."""
    pass


class ApprovalRequiredError(MaaProtocolError):
    """Raised when an action requires human approval."""
    pass


class CostLimitExceededError(MaaProtocolError):
    """Raised when a cost limit is exceeded."""
    pass


class TenantAccessError(MaaProtocolError):
    """Raised when tenant access is denied."""
    pass


class CircuitOpenError(MaaProtocolError):
    """Raised when a circuit breaker is open."""
    pass