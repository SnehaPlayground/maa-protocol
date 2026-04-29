"""Claims and access grant system."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from maa_x.guards.tenant import TenantGate


@dataclass
class Claim:
    subject: str
    resource: str
    action: str


CLAIMS: list[Claim] = []


def grant(subject: str, resource: str, action: str) -> Claim:
    claim = Claim(subject, resource, action)
    CLAIMS.append(claim)
    return claim


def list_claims() -> list[Claim]:
    return list(CLAIMS)


def check_claim(subject: str, resource: str, action: str) -> bool:
    return any(c.subject == subject and c.resource == resource and c.action == action for c in CLAIMS)


def clear_claims() -> None:
    CLAIMS.clear()
