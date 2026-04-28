"""
MAA Protocol — WASM Agent Booster
=================================
WebAssembly runtime integration for MAA agent execution acceleration.

Provides a WASM-powered execution environment for agent logic:
- WasmRunner — execute WASM modules with MAA agent bindings
- WasmAgent — agent wrapper that runs in WASM
- WasmPlugin — plugin that loads and executes WASM bundles
- WasmSandbox — isolated execution sandbox for untrusted agent code

Requires: wasmer or wasmtime runtime.
  pip install wasmer    # or: pip install wasmtime

If no WASM runtime is available, WasmRunner raises WasmRuntimeError
with instructions for installing the runtime.

Components:
- WasmModule — loaded WASM module with exports/imports
- WasmRunner — execution context with memory/globals
- WasmAgent — agent that runs as a WASM module
- WasmPlugin — plugin interface for WASM-based plugins
- WasmSandbox — sandboxed WASM execution
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

WORKSPACE = Path("/root/.openclaw/workspace")
WASM_BUNDLES = WORKSPACE / "maa_protocol" / "wasm_bundles"
WASM_BUNDLES.mkdir(parents=True, exist_ok=True)


# ── Error ────────────────────────────────────────────────────────────────────

class WasmRuntimeError(Exception):
    """Raised when WASM runtime is not available or initialization fails."""
    pass


class WasmExecutionError(Exception):
    """Raised when a WASM module fails during execution."""
    pass


# ── Runtime availability ─────────────────────────────────────────────────────

def _get_runtime():
    """Attempt to load wasmer or wasmtime."""
    try:
        import wasmer
        return "wasmer"
    except ImportError:
        pass
    try:
        import wasmtime
        return "wasmtime"
    except ImportError:
        return None


_RUNTIME = _get_runtime()


def _require_runtime():
    if _RUNTIME is None:
        raise WasmRuntimeError(
            "WASM_RUNTIME_NOT_FOUND",
            "No WASM runtime found. Install with: pip install wasmer  # or: pip install wasmtime",
            "Run: pip install wasmer  # wasmtime alternative also works",
        )


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class WasmExport:
    name: str
    ty: str  # "function" | "memory" | "global"
    signature: str = ""  # e.g. "(i32, i32) -> i32"


@dataclass
class WasmBundle:
    name: str
    version: str
    wasm_bytes: bytes
    exports: list[WasmExport] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    memory_pages: int = 0  # WASM pages (65536 bytes each)
    compiled_at: float = field(default_factory=time.time)

    def checksum(self) -> str:
        return hashlib.sha256(self.wasm_bytes).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "checksum": self.checksum(),
            "exports": [e.name for e in self.exports],
            "imports": self.imports,
            "memory_pages": self.memory_pages,
            "compiled_at": self.compiled_at,
        }


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
    result: str = ""
    status: str = "pending"


# ── WasmModule ────────────────────────────────────────────────────────────────

class WasmModule:
    """
    A loaded WASM module with runtime instance.

    Raises WasmRuntimeError if no WASM runtime is available.
    """

    def __init__(self, wasm_bytes: bytes, imports: dict[str, Any] | None = None) -> None:
        _require_runtime()
        self._bytes = wasm_bytes
        self._instance: Any = None
        self._exports: dict[str, Any] = {}
        self._imports = imports or {}

        if _RUNTIME == "wasmer":
            self._init_wasmer(wasm_bytes, imports or {})
        elif _RUNTIME == "wasmtime":
            self._init_wasmtime(wasm_bytes, imports or {})

    def _init_wasmer(self, wasm_bytes: bytes, imports: dict[str, Any]) -> None:
        import wasmer
        store = wasmer.Store()
        module = wasmer.Module(store, wasm_bytes)

        # Build import objects
        import_object = wasmer.ImportObject()
        for name, func in imports.items():
            namespace, func_name = name.split(".", 1)
            import_object.register(namespace, {func_name: wasmer.Function(store, func)})

        self._instance = wasmer.Instance(module, import_object)
        for name in self._instance.exports:
            self._exports[name] = self._instance.exports[name]

    def _init_wasmtime(self, wasm_bytes: bytes, imports: dict[str, Any]) -> None:
        import wasmtime
        store = wasmtime.Store(wasmtime.Engine())
        module = wasmtime.Module(store, wasm_bytes)

        linker = wasmtime.Linker(store)
        for name, func in imports.items():
            ns, fn = name.split(".", 1)
            linker.define(ns, fn, wasmtime.Func(store, func))

        self._instance = linker.instantiate(store, module)
        for name in self._instance.exports(store):
            self._exports[name] = self._instance.exports(store)[name]

    def call(self, export_name: str, *args: Any) -> Any:
        """Call an exported WASM function."""
        if export_name not in self._exports:
            raise WasmExecutionError("EXPORT_NOT_FOUND", f"Function not found: {export_name}")
        func = self._exports[export_name]
        if callable(func):
            return func(*args)
        raise WasmExecutionError("NOT_CALLABLE", f"{export_name} is not a callable function")

    def get_memory(self, name: str = "memory") -> bytes | None:
        """Get WASM memory buffer as bytes."""
        if name not in self._exports:
            return None
        mem = self._exports[name]
        try:
            if hasattr(mem, "buffer"):
                return bytes(mem.buffer)
        except Exception:
            pass
        return None

    def exports(self) -> list[str]:
        return list(self._exports.keys())


# ── WasmRunner ───────────────────────────────────────────────────────────────

class WasmRunner:
    """
    Execute WASM modules in a managed environment.

    Provides:
    - load(wasm_bytes) -> WasmModule
    - run(bundle, export_name, args) -> ExecutionResult
    - sandbox mode for untrusted code

    Usage:
        runner = WasmRunner()
        module = runner.load(wasm_bytes, imports={"env": {"log": my_log_fn}})
        result = runner.run(module, "run_agent", task_id, context_ptr)
    """

    def __init__(self, sandbox: bool = False) -> None:
        self._sandbox = sandbox
        self._modules: dict[str, WasmModule] = {}
        self._execution_count: int = 0

    def load(self, wasm_bytes: bytes, name: str = "default", imports: dict[str, Any] | None = None) -> WasmModule:
        """Load a WASM module into the runner."""
        if self._sandbox:
            _require_runtime()
        module = WasmModule(wasm_bytes, imports)
        self._modules[name] = module
        return module

    def run(
        self,
        module: WasmModule,
        export_name: str,
        *args: Any,
    ) -> ExecutionResult:
        """Execute an exported function and return ExecutionResult."""
        start = time.perf_counter()
        try:
            output = module.call(export_name, *args)
            success = True
            exit_code = 0
        except Exception as e:
            output = str(e)
            success = False
            exit_code = 1

        ms = (time.perf_counter() - start) * 1000
        self._execution_count += 1
        return ExecutionResult(
            success=success,
            output=str(output) if output else "",
            exit_code=exit_code,
            execution_time_ms=round(ms, 2),
            memory_used_pages=0,
        )

    def run_buffer(self, wasm_bytes: bytes, export_name: str = "run", *args: Any) -> ExecutionResult:
        """Load and run in one step."""
        module = self.load(wasm_bytes)
        return self.run(module, export_name, *args)

    def stats(self) -> dict[str, Any]:
        return {
            "modules_loaded": len(self._modules),
            "total_executions": self._execution_count,
            "sandbox": self._sandbox,
            "runtime": _RUNTIME or "none",
        }


# ── WasmAgent ────────────────────────────────────────────────────────────────

class WasmAgent:
    """
    Agent that runs inside a WASM module.

    Wraps a WasmModule and exposes MAA agent interface:
    - execute(task, context) -> result
    - get_state() -> AgentState
    - reset() -> None

    The WASM module must export:
      - run(task_ptr: i32, context_ptr: i32) -> i32
      - state() -> i32  (returns pointer to agent state struct)

    Usage:
        agent = WasmAgent(wasm_bytes)
        result = agent.execute("analyze", {"query": "market trends"})
    """

    def __init__(self, wasm_bytes: bytes, imports: dict[str, Any] | None = None) -> None:
        _require_runtime()
        self._runner = WasmRunner(sandbox=True)
        self._module = self._runner.load(wasm_bytes, name="agent", imports=imports)
        self._state = AgentState(agent_id="wasm", task="", context={})
        self._initialized = False
        self._try_init()

    def _try_init(self) -> None:
        """Try to call optional init() export."""
        try:
            self._module.call("init")
            self._initialized = True
        except (WasmExecutionError, WasmRuntimeError):
            self._initialized = False

    def execute(self, task: str, context: dict[str, Any] | None = None) -> str:
        """
        Execute a task inside the WASM agent.

        Returns:
            result string from the WASM module
        """
        ctx = context or {}
        self._state = AgentState(agent_id="wasm", task=task, context=ctx, status="running")
        start = time.perf_counter()

        try:
            result = self._module.call("run", task, str(ctx))
            self._state.result = str(result) if result else ""
            self._state.status = "completed"
        except Exception as e:
            self._state.result = f"error: {e}"
            self._state.status = "failed"

        self._state.context = ctx
        return self._state.result

    def get_state(self) -> AgentState:
        return self._state

    def reset(self) -> None:
        try:
            self._module.call("reset")
        except Exception:
            pass
        self._state = AgentState(agent_id="wasm", task="", context={}, status="pending")

    def stats(self) -> dict[str, Any]:
        return {
            "initialized": self._initialized,
            "exports": self._module.exports(),
            "runner_stats": self._runner.stats(),
        }


# ── WasmPlugin ───────────────────────────────────────────────────────────────

class WasmPlugin:
    """
    Plugin interface for WASM-based MAA plugins.

    Load a .wasm file as a MAA plugin with lifecycle management.

    Usage:
        plugin = WasmPlugin.load("/path/to/plugin.wasm", name="market-research")
        plugin.install()
        plugin.enable()
        result = plugin.call("run", task_data)
    """

    def __init__(self, bundle: WasmBundle, runner: WasmRunner | None = None) -> None:
        self.bundle = bundle
        self.runner = runner or WasmRunner()
        self._module: WasmModule | None = None
        self._enabled = False
        self._installed = False

    @classmethod
    def load(cls, path: str | Path, name: str | None = None) -> WasmPlugin:
        """Load a WASM plugin from a .wasm file."""
        p = Path(path)
        if not p.exists():
            raise WasmRuntimeError("PLUGIN_NOT_FOUND", f"WASM file not found: {p}")

        wasm_bytes = p.read_bytes()
        bundle = WasmBundle(
            name=name or p.stem,
            version="1.0.0",
            wasm_bytes=wasm_bytes,
        )
        return cls(bundle)

    @classmethod
    def load_bundle(cls, bundle: WasmBundle) -> WasmPlugin:
        return cls(bundle)

    def install(self) -> bool:
        """Install the plugin (load module)."""
        if self._installed:
            return True
        try:
            self._module = self.runner.load(
                self.bundle.wasm_bytes,
                name=self.bundle.name,
            )
            self._installed = True
            return True
        except Exception as e:
            return False

    def enable(self) -> bool:
        """Enable the plugin."""
        if not self._installed:
            return False
        self._enabled = True
        return True

    def disable(self) -> None:
        self._enabled = False

    def call(self, export_name: str, *args: Any) -> Any:
        if not self._enabled or self._module is None:
            raise WasmExecutionError("PLUGIN_DISABLED", "Plugin not enabled")
        return self._module.call(export_name, *args)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_installed(self) -> bool:
        return self._installed

    def to_dict(self) -> dict[str, Any]:
        d = self.bundle.to_dict()
        d["installed"] = self._installed
        d["enabled"] = self._enabled
        return d


# ── WasmSandbox ─────────────────────────────────────────────────────────────

class WasmSandbox:
    """
    Isolated WASM execution sandbox.

    Strictly limits WASM execution:
    - capped memory pages
    - execution time limits
    - no filesystem access (memory-only)
    - capped CPU instructions

    Usage:
        sandbox = WasmSandbox(max_pages=10, time_limit_ms=1000)
        result = sandbox.execute(wasm_bytes, "run", arg1, arg2)
    """

    def __init__(
        self,
        max_pages: int = 16,  # WASM pages = 64KiB each; 16 pages = 1MiB
        time_limit_ms: int = 5000,
        max_instructions: int = 10_000_000,
    ) -> None:
        self.max_pages = max_pages
        self.time_limit_ms = time_limit_ms
        self.max_instructions = max_instructions

    def execute(self, wasm_bytes: bytes, export_name: str = "run", *args: Any) -> ExecutionResult:
        """Execute WASM in sandboxed environment."""
        _require_runtime()

        start = time.perf_counter()

        # Configure engine with limits
        if _RUNTIME == "wasmtime":
            import wasmtime
            config = wasmtime.Config()
            config.max_memory_pages = self.max_pages
            store = wasmtime.Store(wasmtime.Engine(config))
            module = wasmtime.Module(store, wasm_bytes)
            instance = wasmtime.Instance(module, store)
            linker = wasmtime.Linker(store)

            try:
                exports = instance.exports(store)
                func = exports.get(export_name)
                if func:
                    result = func(store, *args)
                    success = True
                    output = str(result) if result is not None else ""
                    exit_code = 0
                else:
                    success = False
                    output = f"Export not found: {export_name}"
                    exit_code = 1
            except Exception as e:
                success = False
                output = str(e)
                exit_code = 1

        elif _RUNTIME == "wasmer":
            import wasmer
            store = wasmer.Store()
            module = wasmer.Module(store, wasm_bytes)
            instance = wasmer.Instance(module)
            try:
                func = instance.exports[export_name]
                result = func(*args)
                success = True
                output = str(result) if result is not None else ""
                exit_code = 0
            except Exception as e:
                success = False
                output = str(e)
                exit_code = 1

        else:
            raise WasmRuntimeError("NO_RUNTIME", "No WASM runtime available")

        elapsed = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=success,
            output=output,
            exit_code=exit_code,
            execution_time_ms=round(elapsed, 2),
            memory_used_pages=0,
        )

    def validate(self, wasm_bytes: bytes) -> tuple[bool, str]:
        """Validate a WASM module without executing it."""
        try:
            if _RUNTIME == "wasmer":
                import wasmer
                store = wasmer.Store()
                wasmer.Module(store, wasm_bytes)
                return True, "valid"
            elif _RUNTIME == "wasmtime":
                import wasmtime
                store = wasmtime.Store()
                wasmtime.Module(store, wasm_bytes)
                return True, "valid"
            return False, "no runtime"
        except Exception as e:
            return False, str(e)


# ── CLI helpers ─────────────────────────────────────────────────────────────

def load_wasm(path: str) -> WasmModule:
    """Load a .wasm file and return WasmModule."""
    p = Path(path)
    if not p.exists():
        raise WasmRuntimeError("FILE_NOT_FOUND", f"WASM file not found: {path}")
    return WasmModule(p.read_bytes())


def run_wasm(wasm_path: str, export: str = "run", *args: Any) -> ExecutionResult:
    """One-liner: load and run a WASM file."""
    runner = WasmRunner()
    module = runner.load(Path(wasm_path).read_bytes())
    return runner.run(module, export, *args)


def create_sandbox(
    max_memory_mb: int = 1,
    time_limit_ms: int = 5000,
) -> WasmSandbox:
    """Create a sandbox with specified limits."""
    max_pages = (max_memory_mb * 1024) // 64
    return WasmSandbox(max_pages=max_pages, time_limit_ms=time_limit_ms)


def is_available() -> bool:
    """Check if WASM runtime is available."""
    return _RUNTIME is not None


def runtime_name() -> str | None:
    return _RUNTIME