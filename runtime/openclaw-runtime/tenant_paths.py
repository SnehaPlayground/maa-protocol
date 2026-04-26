#!/usr/bin/env python3
"""
TenantPathResolver — resolves all workspace paths based on tenant context.
Ensures agents always write to the correct tenant-scoped path.
"""
import os
from pathlib import Path
from tenant_context import TenantContext, DEFAULT_TENANT

WORKSPACE_ROOT = Path("/root/.openclaw/workspace")
TENANTS_ROOT = WORKSPACE_ROOT / "tenants"

# Fallback legacy paths (backward compat)
LEGACY_TASKS_DIR = WORKSPACE_ROOT / "ops/multi-agent-orchestrator/tasks"
LEGACY_LOGS_DIR = WORKSPACE_ROOT / "ops/multi-agent-orchestrator/logs"
LEGACY_OUTPUTS_DIR = WORKSPACE_ROOT / "data/reports"


class TenantPathResolver:
    """
    Resolves paths for a specific tenant context.

    Resource types:
        tasks       → tenant-specific task state files
        logs        → completion markers, validation reports, progress signals
        outputs     → agent output files
        metrics     → per-tenant metrics store
        audit       → per-tenant audit trail
        config      → operator/client config files
    """

    RESOURCE_TYPES = {"tasks", "logs", "outputs", "metrics", "audit", "config"}

    def __init__(self, tenant: TenantContext):
        self.tenant = tenant

    def resolve(self, resource_type: str) -> Path:
        """Get the base path for a resource type under this tenant."""
        from urllib.parse import unquote
        if resource_type not in self.RESOURCE_TYPES:
            raise ValueError(f"Unknown resource type: {resource_type}")
        # Security check FIRST: validate tenant components before calling _base_path.
        # This catches path traversals in operator_id/client_id before any path is built.
        for component in (self.tenant.operator_id, self.tenant.client_id):
            decoded = unquote(component)
            if '..' in decoded or decoded.startswith('/') or decoded.startswith('\\'):
                raise ValueError(
                    f"Security violation: tenant component {component!r} "
                    f"decodes to {decoded!r} which is a path traversal. Rejected."
                )
        base = self._base_path(resource_type)
        # Validate the resolved path stays under TENANTS_ROOT.
        # For legacy paths (default tenant), resolve() may return workspace root —
        # in that case, resolve() already returned base which may be outside TENANTS_ROOT.
        # Only enforce TENANTS_ROOT boundary for non-legacy (tenant-scoped) paths.
        if not self.tenant.is_default():
            real = base.resolve()
            if not str(real).startswith(str(TENANTS_ROOT)):
                raise ValueError(
                    f"Security violation: tenant path {real} escapes TENANTS_ROOT "
                    f"{TENANTS_ROOT}. Tenant_id may not be used for path escape."
                )
        return base

    def resolve_task_file(self, task_id: str) -> Path:
        """Get the full path for a task state file."""
        return self.resolve("tasks") / f"{task_id}.json"

    def resolve_log_file(self, task_id: str, suffix: str) -> Path:
        """Get the full path for a log/marker file (e.g. .completion, .validation)."""
        return self.resolve("logs") / f"{task_id}.{suffix}"

    def resolve_output_file(self, task_id: str, extension: str = ".txt") -> Path:
        """Get the full path for an agent output file."""
        return self.resolve("outputs") / f"{task_id}{extension}"

    def _base_path(self, resource_type: str) -> Path:
        if self.tenant.is_default():
            return self._legacy_path(resource_type)
        op = self.tenant.operator_id
        cl = self.tenant.client_id
        if resource_type == "config":
            if self.tenant.is_operator_level():
                return TENANTS_ROOT / op / "config" / "operator.json"
            return TENANTS_ROOT / op / "clients" / cl / "config" / "client.json"
        if resource_type == "metrics":
            if self.tenant.is_operator_level():
                return TENANTS_ROOT / op / "metrics" / "operator_metrics.json"
            return TENANTS_ROOT / op / "clients" / cl / "metrics" / "tenant_metrics.json"
        if resource_type == "audit":
            return TENANTS_ROOT / op / "audit"
        if resource_type == "logs":
            if self.tenant.is_operator_level():
                return TENANTS_ROOT / op / "logs"
            return TENANTS_ROOT / op / "clients" / cl / "logs"
        if resource_type == "outputs":
            if self.tenant.is_operator_level():
                return TENANTS_ROOT / op / "outputs"
            return TENANTS_ROOT / op / "clients" / cl / "outputs"
        # tasks
        if self.tenant.is_operator_level():
            return TENANTS_ROOT / op / "tasks"
        return TENANTS_ROOT / op / "clients" / cl / "tasks"

    def _legacy_path(self, resource_type: str) -> Path:
        """Fallback to legacy paths for the default tenant."""
        return {
            "tasks":   LEGACY_TASKS_DIR,
            "logs":    LEGACY_LOGS_DIR,
            "outputs": LEGACY_OUTPUTS_DIR,
            "metrics": LEGACY_OUTPUTS_DIR.parent / "metrics",
            "audit":   LEGACY_LOGS_DIR.parent / "audit",
            "config":  LEGACY_TASKS_DIR.parent / "config",
        }.get(resource_type, LEGACY_TASKS_DIR)

    def ensure_dirs(self) -> None:
        """Create all tenant directories if they don't exist.
        
        GAP 4 fix: config resolves to a FILE path (not a dir), so mkdir
        would create a directory of the same name. Use parent.mkdir for
        config resource. Also remove stale files that block directory creation.
        """
        for rt in self.RESOURCE_TYPES:
            p = self.resolve(rt)
            try:
                if rt == "config":
                    # config resolves to a FILE — create its parent directory
                    p.parent.mkdir(parents=True, exist_ok=True)
                    continue
                if p.exists() and not p.is_dir():
                    p.unlink()  # Remove stale file blocking directory creation
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                print(f"[TenantPathResolver] WARNING: could not create {p}: {e}")

    def tenant_dir(self) -> Path:
        """The root directory for this tenant."""
        if self.tenant.is_default():
            return WORKSPACE_ROOT
        return TENANTS_ROOT / self.tenant.operator_id


def resolve_path(tenant: TenantContext, resource_type: str) -> Path:
    """Convenience function with path-escape protection."""
    resolver = TenantPathResolver(tenant)
    return resolver.resolve(resource_type)  # resolve() now does the security check