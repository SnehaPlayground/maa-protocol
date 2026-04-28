from dataclasses import dataclass
from typing import Any

@dataclass
class ProviderSpec:
    name: str
    api: str
    supports_stream: bool = True
    supports_tools: bool = True

PROVIDERS = {
    'default': ProviderSpec(name='default', api='openclaw-default'),
    'codex': ProviderSpec(name='codex', api='openai-codex-responses'),
    'gguf': ProviderSpec(name='gguf', api='local-gguf', supports_tools=False),
}

def list_providers() -> list[ProviderSpec]:
    return list(PROVIDERS.values())

def get_provider(name: str = 'default') -> ProviderSpec:
    return PROVIDERS.get(name, PROVIDERS['default'])
