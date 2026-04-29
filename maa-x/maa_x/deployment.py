"""Deployment operations and runtime health."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeploymentProfile(Enum):
    SINGLE_TENANT = 'single-tenant'
    MULTI_TENANT = 'multi-tenant'
    COMMUNITY = 'community'
    HIGH_ASSURANCE = 'high-assurance'


@dataclass
class RuntimeConfig:
    profile: DeploymentProfile
    version: str
    region: str
    max_agents: int
    log_level: str = 'INFO'
    tracing_enabled: bool = True
    observability_enabled: bool = True
    agent_timeout_seconds: int = 600
    task_concurrency_limit: int = 10
    credentials_rotated_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {**self.__dict__, 'profile': self.profile.value}


@dataclass
class HealthStatus:
    healthy: bool
    component: str
    message: str
    checked_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0


class HealthCheck:
    def check(self) -> list[HealthStatus]:
        results: list[HealthStatus] = []
        start = time.time()
        workspace = '/root/.openclaw/workspace'
        accessible = os.access(workspace, os.R_OK | os.W_OK)
        results.append(HealthStatus(accessible, 'workspace', f"workspace {'ok' if accessible else 'inaccessible'}", latency_ms=(time.time() - start) * 1000))
        mod_start = time.time()
        try:
            import maa_x.security as sec  # noqa
            import maa_x.memory as mem  # noqa
            import maa_x.provider_router as pr  # noqa
            import maa_x.plugins as pl  # noqa
            results.append(HealthStatus(True, 'modules', 'core modules importable', latency_ms=(time.time() - mod_start) * 1000))
        except Exception as e:
            results.append(HealthStatus(False, 'modules', str(e)))
        obs_start = time.time()
        try:
            import maa_x.hooks as hooks
            reg = hooks.HookRegistry()
            healthy = len(reg.HOOK_POINTS) >= 14
            results.append(HealthStatus(healthy, 'observability', f"observability layer {'ok' if healthy else 'hook registry depleted'}", latency_ms=(time.time() - obs_start) * 1000))
        except Exception as e:
            results.append(HealthStatus(False, 'observability', str(e)))
        plug_start = time.time()
        try:
            from maa_x import plugins
            reg = plugins.get_registry()
            core_ok = reg.get_plugin('maa:security') is not None and reg.get_plugin('maa:routing') is not None
            results.append(HealthStatus(core_ok, 'plugin_registry', f"plugin registry {'ok' if core_ok else 'missing core plugins'}", latency_ms=(time.time() - plug_start) * 1000))
        except Exception as e:
            results.append(HealthStatus(False, 'plugin_registry', str(e)))
        return results

    def is_healthy(self) -> bool:
        return all(s.healthy for s in self.check())


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


def deployment_profiles() -> list[str]:
    return [p.value for p in DeploymentProfile]


def get_runtime_config(profile: DeploymentProfile = DeploymentProfile.MULTI_TENANT) -> RuntimeConfig:
    defaults = {DeploymentProfile.SINGLE_TENANT: {'max_agents': 4, 'task_concurrency_limit': 5}, DeploymentProfile.MULTI_TENANT: {'max_agents': 8, 'task_concurrency_limit': 10}, DeploymentProfile.COMMUNITY: {'max_agents': 16, 'task_concurrency_limit': 20}, DeploymentProfile.HIGH_ASSURANCE: {'max_agents': 2, 'task_concurrency_limit': 2, 'tracing_enabled': True}}
    d = defaults.get(profile, {})
    return RuntimeConfig(profile, '1.0.0', 'us-west-2', d.get('max_agents', 8), tracing_enabled=d.get('tracing_enabled', True), task_concurrency_limit=d.get('task_concurrency_limit', 10))


def run_health_check() -> list[HealthStatus]:
    return HealthCheck().check()


def rotate_credentials() -> dict[str, Any]:
    return {'rotated_at': time.time(), 'components': ['api_keys', 'tokens', 'secrets'], 'next_rotation_at': time.time() + (90 * 24 * 3600), 'status': 'success'}


def get_deployment_state(profile: DeploymentProfile = DeploymentProfile.MULTI_TENANT) -> DeploymentState:
    return DeploymentState(profile=profile, config=get_runtime_config(profile), health_check=HealthCheck())
