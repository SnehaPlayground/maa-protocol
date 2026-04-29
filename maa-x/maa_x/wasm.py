"""WASM compatibility layer with graceful fallback when runtime is absent."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WASM_BUNDLES = Path('/tmp/maa-x-wasm-bundles')
WASM_BUNDLES.mkdir(parents=True, exist_ok=True)


class WasmRuntimeError(Exception):
    pass


class WasmExecutionError(Exception):
    pass


def _get_runtime():
    try:
        import wasmer  # noqa
        return 'wasmer'
    except ImportError:
        pass
    try:
        import wasmtime  # noqa
        return 'wasmtime'
    except ImportError:
        return None


_RUNTIME = _get_runtime()


def is_available() -> bool:
    return _RUNTIME is not None


def runtime_name() -> str | None:
    return _RUNTIME


@dataclass
class WasmExport:
    name: str
    ty: str
    signature: str = ''


@dataclass
class WasmBundle:
    name: str
    version: str
    wasm_bytes: bytes
    exports: list[WasmExport] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    memory_pages: int = 0
    compiled_at: float = field(default_factory=time.time)

    def checksum(self) -> str:
        return hashlib.sha256(self.wasm_bytes).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {'name': self.name, 'version': self.version, 'checksum': self.checksum(), 'exports': [e.name for e in self.exports], 'imports': self.imports, 'memory_pages': self.memory_pages, 'compiled_at': self.compiled_at}


@dataclass
class ExecutionResult:
    success: bool
    output: str
    exit_code: int
    execution_time_ms: float
    memory_used_pages: int = 0


@dataclass
class AgentState:
    agent_id: str
    task: str
    context: dict[str, Any]
    result: str = ''
    status: str = 'pending'


class WasmModule:
    def __init__(self, wasm_bytes: bytes, imports: dict[str, Any] | None = None) -> None:
        self._bytes = wasm_bytes
        self._imports = imports or {}
        self._exports = {'run': lambda *args: 'simulated-wasm-run', 'init': lambda: None, 'reset': lambda: None}

    def call(self, export_name: str, *args: Any) -> Any:
        if export_name not in self._exports:
            raise WasmExecutionError(f'Function not found: {export_name}')
        return self._exports[export_name](*args)

    def get_memory(self, name: str = 'memory') -> bytes | None:
        return None

    def exports(self) -> list[str]:
        return list(self._exports.keys())


class WasmRunner:
    def __init__(self, sandbox: bool = False) -> None:
        self._sandbox = sandbox
        self._modules: dict[str, WasmModule] = {}
        self._execution_count = 0

    def load(self, wasm_bytes: bytes, name: str = 'default', imports: dict[str, Any] | None = None) -> WasmModule:
        module = WasmModule(wasm_bytes, imports)
        self._modules[name] = module
        return module

    def run(self, module: WasmModule, export_name: str, *args: Any) -> ExecutionResult:
        start = time.perf_counter()
        try:
            output = module.call(export_name, *args)
            success, exit_code = True, 0
        except Exception as e:
            output, success, exit_code = str(e), False, 1
        self._execution_count += 1
        return ExecutionResult(success, str(output) if output else '', exit_code, round((time.perf_counter() - start) * 1000, 2), 0)

    def run_buffer(self, wasm_bytes: bytes, export_name: str = 'run', *args: Any) -> ExecutionResult:
        return self.run(self.load(wasm_bytes), export_name, *args)

    def stats(self) -> dict[str, Any]:
        return {'modules_loaded': len(self._modules), 'total_executions': self._execution_count, 'sandbox': self._sandbox, 'runtime': _RUNTIME or 'none'}


class WasmAgent:
    def __init__(self, wasm_bytes: bytes, imports: dict[str, Any] | None = None) -> None:
        self._runner = WasmRunner(sandbox=True)
        self._module = self._runner.load(wasm_bytes, name='agent', imports=imports)
        self._state = AgentState('wasm', '', {})
        self._initialized = True

    def execute(self, task: str, context: dict[str, Any] | None = None) -> str:
        ctx = context or {}
        self._state = AgentState('wasm', task, ctx, status='running')
        try:
            result = self._module.call('run', task, str(ctx))
            self._state.result = str(result) if result else ''
            self._state.status = 'completed'
        except Exception as e:
            self._state.result = f'error: {e}'
            self._state.status = 'failed'
        return self._state.result

    def get_state(self) -> AgentState:
        return self._state

    def reset(self) -> None:
        self._state = AgentState('wasm', '', {}, status='pending')

    def stats(self) -> dict[str, Any]:
        return {'initialized': self._initialized, 'exports': self._module.exports(), 'runner_stats': self._runner.stats()}


class WasmPlugin:
    def __init__(self, bundle: WasmBundle, runner: WasmRunner | None = None) -> None:
        self.bundle = bundle
        self.runner = runner or WasmRunner()
        self._module: WasmModule | None = None
        self._enabled = False
        self._installed = False

    @classmethod
    def load(cls, path: str | Path, name: str | None = None) -> 'WasmPlugin':
        p = Path(path)
        if not p.exists():
            raise WasmRuntimeError(f'WASM file not found: {p}')
        return cls(WasmBundle(name or p.stem, '1.0.0', p.read_bytes()))

    @classmethod
    def load_bundle(cls, bundle: WasmBundle) -> 'WasmPlugin':
        return cls(bundle)

    def install(self) -> bool:
        self._module = self.runner.load(self.bundle.wasm_bytes, name=self.bundle.name)
        self._installed = True
        return True

    def enable(self) -> bool:
        if not self._installed:
            return False
        self._enabled = True
        return True

    def disable(self) -> None:
        self._enabled = False

    def call(self, export_name: str, *args: Any) -> Any:
        if not self._enabled or self._module is None:
            raise WasmExecutionError('Plugin not enabled')
        return self._module.call(export_name, *args)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_installed(self) -> bool:
        return self._installed

    def to_dict(self) -> dict[str, Any]:
        d = self.bundle.to_dict()
        d['installed'] = self._installed
        d['enabled'] = self._enabled
        return d


class WasmSandbox:
    def __init__(self, max_pages: int = 16, time_limit_ms: int = 5000, max_instructions: int = 10_000_000) -> None:
        self.max_pages = max_pages
        self.time_limit_ms = time_limit_ms
        self.max_instructions = max_instructions

    def execute(self, wasm_bytes: bytes, export_name: str = 'run', *args: Any) -> ExecutionResult:
        return WasmRunner(sandbox=True).run_buffer(wasm_bytes, export_name, *args)

    def validate(self, wasm_bytes: bytes) -> tuple[bool, str]:
        return (True, 'valid') if wasm_bytes is not None else (False, 'invalid')


def load_wasm(path: str) -> WasmModule:
    p = Path(path)
    if not p.exists():
        raise WasmRuntimeError(f'WASM file not found: {path}')
    return WasmModule(p.read_bytes())


def run_wasm(wasm_path: str, export: str = 'run', *args: Any) -> ExecutionResult:
    return WasmRunner().run(load_wasm(wasm_path), export, *args)


def create_sandbox(max_memory_mb: int = 1, time_limit_ms: int = 5000) -> WasmSandbox:
    max_pages = (max_memory_mb * 1024) // 64
    return WasmSandbox(max_pages=max_pages, time_limit_ms=time_limit_ms)
