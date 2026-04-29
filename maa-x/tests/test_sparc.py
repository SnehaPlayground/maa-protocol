"""Tests for maa_x.sparc module."""

import pytest
from maa_x.sparc import SPARCEngine, SPARCExecution, run_sparc


def test_sparc_execute_no_executor():
    engine = SPARCEngine()
    result = engine.execute("build a REST API")
    assert isinstance(result, SPARCExecution)
    assert result.task == "build a REST API"
    assert len(result.steps) > 0


def test_sparc_execute_with_executor():
    def executor(action: str):
        return (f"observed: {action}", {"done": True}, 0.95)

    engine = SPARCEngine(confidence_threshold=0.85)
    result = engine.execute("complex task", executor=executor)
    assert result.outcome == "success"


def test_sparc_execute_low_confidence():
    def executor(action: str):
        return (f"observed: {action}", {"partial": True}, 0.5)

    engine = SPARCEngine(max_iterations=3, confidence_threshold=0.9)
    result = engine.execute("task", executor=executor)
    assert result.outcome in ("simulated", None)  # falls back after iterations


def test_run_sparc_convenience():
    result = run_sparc("quick task")
    assert isinstance(result, SPARCExecution)
    assert result.task == "quick task"


def test_sparc_phases_present():
    engine = SPARCEngine()
    result = engine.execute("test task")
    phases = {s.phase for s in result.steps}
    assert "plan" in phases
    assert "act" in phases