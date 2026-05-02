"""Custom exceptions for Maa Protocol."""


class MaaProtocolError(Exception):
    """Base exception for Maa Protocol errors."""


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



class PersistenceError(MaaProtocolError):
    """Raised when a persistence backend cannot complete an operation."""


class TenantIsolationError(PersistenceError):
    """Raised when cross-tenant data access is attempted."""



class CostValidationError(ValueError):
    """Raised when a CostGuard parameter or input value is invalid."""