"""Tests for maa_x.mcp module."""

import pytest
from maa_x.mcp import list_tools, get_tool, search_tools, mcp_capabilities, MCPTool


def test_list_tools():
    tools = list_tools()
    assert len(tools) > 0
    assert "swarm_init" in tools


def test_get_tool():
    tool = get_tool("swarm_init")
    assert tool is not None
    assert isinstance(tool, MCPTool)
    assert tool.name == "swarm_init"


def test_get_tool_unknown():
    tool = get_tool("nonexistent_tool_xyz")
    assert tool is None


def test_search_tools():
    results = search_tools("swarm")
    assert len(results) > 0
    assert all("swarm" in t.name or "swarm" in t.description for t in results)


def test_search_all():
    results = search_tools("")
    assert len(results) > 0


def test_mcp_capabilities():
    caps = mcp_capabilities()
    assert caps["tool_count"] > 0
    assert "group_count" in caps
    assert "mode_count" in caps
    assert "transports" in caps


def test_tool_to_dict():
    tool = get_tool("swarm_init")
    d = tool.to_dict()
    assert d["name"] == "swarm_init"
    assert "category" in d
    assert "description" in d