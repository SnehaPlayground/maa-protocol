"""
MAA Protocol — Deployment Operations
====================================
Deployment profiles, health checks, runtime config, and operational tooling.

Profiles:
- SINGLE_TENANT — dedicated instance per tenant
- MULTI_TENANT — shared instance, tenant-isolated via context
- COMMUNITY — shared instance, open
- HIGH_ASSURANCE — air-gapped, strict controls

Components:
- DeploymentProfile enum
- RuntimeConfig — active configuration snapshot
- HealthCheck — operational health probes
- DeploymentState — tracking of running instances
- deploy() / rollback() / health_check() API
- rotate_credentials() — credential rotation for high-assurance
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Deployment profile ────────────────────────────────────────────────────────

class DeploymentProfile(Enum):
    SINGLE_TENANT = "single-tenant"      # dedicated per tenant
    MULTI_TENANT = "multi-tenant"        # shared, tenant-isolated
    COMMUNITY = "community"              # shared, open
    HIGH_ASSURANCE = "high-assurance"    # air-gapped, strict


# ── Runtime configuration ─────────────────────────────────────────────────────

@dataclass
class RuntimeConfig:
    profile: DeploymentProfile
    version: str
    region: str
    max_agents: int
    log_level: str = "INFO"
    tracing_enabled: bool = True
    observability_enabled: bool = True
    agent_timeout_seconds: int = 600
    task_concurrency_limit: int = 10
    credentials_rotated_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.value,
            "version": self.version,
            "region": self.region,
            "max_agents": self.max_agents,
            "log_level": self.log_level,
            "tracing_enabled": self.tracing_enabled,
            "observability_enabled": self.observability_enabled,
            "agent_timeout_seconds": self.agent_timeout_seconds,
            "task_concurrency_limit": self.task_concurrency_limit,
            "credentials_rotated_at": self.credentials_rotated_at,
        }


# ── Health check ─────────────────────────────────────────────────────────────

@dataclass
class HealthStatus:
    healthy: bool
    component: str
    message: str
    checked_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0


class HealthCheck:
    """
    Operational health probes.

    Checks:
    - workspace filesystem accessible
    - maa_protocol modules importable
    - observability layer reachable
    - plugin registry functional
    """

    def check(self) -> list[HealthStatus]:
        results: list[HealthStatus] = []
        start = time.time()

        # Check workspace filesystem
        try:
            import os
            workspace = "/root/.openclaw/workspace"
            accessible = os.access(workspace, os.R_OK | os.W_OK)
            results.append(HealthStatus(
                healthy=accessible,
                component="workspace",
                message=f"workspace {'ok' if accessible else 'inaccessible'}",
                latency_ms=(time.time() - start) * 1000,
            ))
        except Exception as e:
            results.append(HealthStatus(False, "workspace", str(e)))

        # Check modules import
        mod_start = time.time()
        try:
            import maa_protocol.security as sec
            import maa_protocol.memory as mem
            import maa_protocol.provider_router as pr
            import maa_protocol.plugins as pl
            results.append(HealthStatus(
                healthy=True, component="modules",
                message="core modules importable",
                latency_ms=(time.time() - mod_start) * 1000,
            ))
        except Exception as e:
            results.append(HealthStatus(False, "modules", str(e)))

        # Check observability
        obs_start = time.time()
        try:
            import maa_protocol.hooks as hooks
            reg = hooks.HookRegistry()
            healthy = len(reg.HOOK_POINTS) >= 14
            results.append(HealthStatus(
                healthy=healthy, component="observability",
                message=f"observability layer {'ok' if healthy else 'hook registry depleted'}",
                latency_ms=(time.time() - obs_start) * 1000,
            ))
        except Exception as e:
            results.append(HealthStatus(False, "observability", str(e)))

        # Check plugin registry
        plug_start = time.time()
        try:
            from maa_protocol import plugins
            reg = plugins.get_registry()
            core_ok = reg.is_registered("maa:security") and reg.is_registered("maa:routing")
            results.append(HealthStatus(
                healthy=core_ok, component="plugin_registry",
                message=f"plugin registry {'ok' if core_ok else 'missing core plugins'}",
                latency_ms=(time.time() - plug_start) * 1000,
            ))
        except Exception as e:
            results.append(HealthStatus(False, "plugin_registry", str(e)))

        return results

    def is_healthy(self) -> bool:
        return all(s.healthy for s in self.check())


# ── Deployment state ───────────────────────────────────────────────────────────

@dataclass
class DeploymentState:
    profile: DeploymentProfile
    config: RuntimeConfig
    started_at: float = field(default_factory=time.time)
    health_check: HealthCheck = field(default_factory=HealthCheck)
    deployments: dict[str, Any] = field(default_factory=dict)

    def is_healthy(self) -> bool:
        return self.health_check.is_healthy()

    def uptime_seconds(self) -> float:
        return time.time() - self.started_at


# ── Deployment operations ─────────────────────────────────────────────────────

def deployment_profiles() -> list[str]:
    return [p.value for p in DeploymentProfile]


def get_runtime_config(profile: DeploymentProfile = DeploymentProfile.MULTI_TENANT) -> RuntimeConfig:
    """Return default runtime config for a profile."""
    defaults = {
        DeploymentProfile.SINGLE_TENANT: {"max_agents": 4, "task_concurrency_limit": 5},
        DeploymentProfile.MULTI_TENANT: {"max_agents": 8, "task_concurrency_limit": 10},
        DeploymentProfile.COMMUNITY: {"max_agents": 16, "task_concurrency_limit": 20},
        DeploymentProfile.HIGH_ASSURANCE: {"max_agents": 2, "task_concurrency_limit": 2, "tracing_enabled": True},
    }
    d = defaults.get(profile, {})
    return RuntimeConfig(
        profile=profile,
        version="1.0.0",
        region="us-west-2",
        max_agents=d.get("max_agents", 8),
        agent_timeout_seconds=600,
        task_concurrency_limit=d.get("task_concurrency_limit", 10),
        tracing_enabled=d.get("tracing_enabled", True),
    )


def run_health_check() -> list[HealthStatus]:
    return HealthCheck().check()


def rotate_credentials() -> dict[str, Any]:
    """Simulate credential rotation. Returns rotation metadata."""
    return {
        "rotated_at": time.time(),
        "components": ["api_keys", "tokens", "secrets"],
        "next_rotation_at": time.time() + (90 * 24 * 3600),  # 90 days
        "status": "success",
    }


def get_deployment_state(profile: DeploymentProfile = DeploymentProfile.MULTI_TENANT) -> DeploymentState:
    config = get_runtime_config(profile)
    return DeploymentState(profile=profile, config=config, health_check=HealthCheck())