"""Provider specification and registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ProviderSpec:
    name: str
    api: str
    supports_stream: bool = True
    supports_tools: bool = True


PROVIDERS: dict[str, ProviderSpec] = {}


def register_provider(spec: ProviderSpec) -> None:
    PROVIDERS[spec.name] = spec


def list_providers() -> list[ProviderSpec]:
    return list(PROVIDERS.values())


def get_provider(name: str = 'default') -> ProviderSpec:
    return PROVIDERS.get(name, PROVIDERS.get('default', ProviderSpec(name=name, api='unknown')))


# Seed default providers
for _name, _api, _stream, _tools in [
    ('default', 'openclaw-default', True, True),
    ('codex', 'openai-codex-responses', True, True),
    ('gguf', 'local-gguf', True, False),
]:
    PROVIDERS[_name] = ProviderSpec(name=_name, api=_api, supports_stream=_stream, supports_tools=_tools)
