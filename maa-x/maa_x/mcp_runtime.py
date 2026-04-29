"""Minimal MCP runtime wrapper over the MCP registry."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from maa_x.mcp import get_tool, list_tools


@dataclass
class MCPRequest:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    session_id: str | None = None
    created_at: float = field(default_factory=time.time)


@dataclass
class MCPResponse:
    ok: bool
    tool: str
    request_id: str | None
    result: Any = None
    error: str | None = None
    completed_at: float = field(default_factory=time.time)


class MCPRuntime:
    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}
        self._sessions: dict[str, dict[str, Any]] = {}

    def register_handler(self, tool: str, handler: Any) -> None:
        self._handlers[tool] = handler

    def create_session(self, session_id: str) -> None:
        self._sessions.setdefault(session_id, {"created_at": time.time(), "calls": 0})

    def call(self, request: MCPRequest) -> MCPResponse:
        tool = get_tool(request.tool)
        if tool is None:
            return MCPResponse(False, request.tool, request.request_id, error='tool not found')
        handler = self._handlers.get(request.tool)
        if handler is None:
            return MCPResponse(True, request.tool, request.request_id, result={"tool": tool.to_dict(), "arguments": request.arguments})
        try:
            if request.session_id:
                self.create_session(request.session_id)
                self._sessions[request.session_id]["calls"] += 1
            return MCPResponse(True, request.tool, request.request_id, result=handler(request.arguments))
        except Exception as e:
            return MCPResponse(False, request.tool, request.request_id, error=str(e))

    def capabilities(self) -> dict[str, Any]:
        return {"registered_tools": list_tools(), "handler_count": len(self._handlers), "session_count": len(self._sessions)}
