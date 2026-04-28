"""
MAA Protocol — Codex Dual-Mode Collaboration
=============================================
Real dual-mode (Codex + Claude) workflow orchestration.
Modes: REVIEW (Claude reviews, Codex implements) and CASCADE (Codex first, Claude evaluates).
Capabilities: task decomposition, mode selection, cross-agent coordination, result merge.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ── Mode and role definitions ─────────────────────────────────────────────────

class CollaborationMode(Enum):
    REVIEW = "review"     # Claude reviews, Codex implements
    CASCADE = "cascade"   # Codex first pass, Claude evaluates
    PARALLEL = "parallel" # Both work simultaneously
    HANDOVER = "handover" # Codex → Claude → Codex


class CodexAgentRole(Enum):
    ARCHITECT = "architect"    # design and structure
    CODER = "coder"            # implementation
    REVIEWER = "reviewer"       # code review
    TESTER = "tester"          # test generation


@dataclass
class DualModeTask:
    claude_role: str
    codex_role: str
    namespace: str = "collaboration"
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "claude_role": self.claude_role,
            "codex_role": self.codex_role,
            "namespace": self.namespace,
            "description": self.description,
        }


# ── Task decomposition ─────────────────────────────────────────────────────────

@dataclass
class TaskSegment:
    id: str
    description: str
    assigned_agent: str  # "claude" or "codex"
    mode: CollaborationMode
    priority: int = 1
    status: str = "pending"  # pending/in_progress/done/failed
    output: str | None = None
    duration_ms: float | None = None


@dataclass
class DecomposedTask:
    original_prompt: str
    segments: list[TaskSegment]
    mode: CollaborationMode
    estimated_duration_ms: float = 0.0

    def pending_count(self) -> int:
        return sum(1 for s in self.segments if s.status == "pending")

    def done_count(self) -> int:
        return sum(1 for s in self.segments if s.status == "done")


# ── Mode selector ──────────────────────────────────────────────────────────────

class ModeSelector:
    """
    Analyzes a task prompt and selects the appropriate collaboration mode.

    Heuristics:
    - REVIEW: when code implementation is primary ask (contains "implement",
      "write code", "build", "create function", "develop")
    - CASCADE: when quality/correctness is primary concern (contains "review",
      "audit", "validate", "improve", "refactor", "debug")
    - PARALLEL: when independent subtasks exist
    - HANDOVER: when complex multi-pass refinement needed
    """

    REVIEW_SIGNALS = ["implement", "write code", "build", "create function", "develop", "write a script"]
    CASCADE_SIGNALS = ["review", "audit", "validate", "improve", "refactor", "debug", "check for bugs"]
    PARALLEL_SIGNALS = ["both", "parallel", "simultaneously", "all of these"]
    HANDOVER_SIGNALS = ["iterate", "refine", "handover", "collaborate", "pass back"]

    def select_mode(self, prompt: str) -> CollaborationMode:
        prompt_lower = prompt.lower()

        if any(s in prompt_lower for s in self.CASCADE_SIGNALS):
            return CollaborationMode.CASCADE

        if any(s in prompt_lower for s in self.REVIEW_SIGNALS):
            return CollaborationMode.REVIEW

        if any(s in prompt_lower for s in self.PARALLEL_SIGNALS):
            return CollaborationMode.PARALLEL

        if any(s in prompt_lower for s in self.HANDOVER_SIGNALS):
            return CollaborationMode.HANDOVER

        # Default: REVIEW for code tasks, CASCADE for docs/analysis
        if any(w in prompt_lower for w in ["code", "function", "class", "script", "api"]):
            return CollaborationMode.REVIEW
        return CollaborationMode.CASCADE

    def decompose_task(self, prompt: str, mode: CollaborationMode) -> DecomposedTask:
        segments = []

        if mode == CollaborationMode.REVIEW:
            segments = [
                TaskSegment(id="s1", description="Claude reviews and specifies requirements",
                           assigned_agent="claude", mode=mode, priority=1),
                TaskSegment(id="s2", description="Codex implements based on spec",
                           assigned_agent="codex", mode=mode, priority=2),
                TaskSegment(id="s3", description="Claude reviews implementation",
                           assigned_agent="claude", mode=mode, priority=3),
            ]
        elif mode == CollaborationMode.CASCADE:
            segments = [
                TaskSegment(id="s1", description="Codex initial implementation",
                           assigned_agent="codex", mode=mode, priority=1),
                TaskSegment(id="s2", description="Claude evaluates and provides feedback",
                           assigned_agent="claude", mode=mode, priority=2),
                TaskSegment(id="s3", description="Codex refines based on feedback",
                           assigned_agent="codex", mode=mode, priority=3),
            ]
        elif mode == CollaborationMode.PARALLEL:
            segments = [
                TaskSegment(id="s1", description="Codex independent pass",
                           assigned_agent="codex", mode=mode, priority=1),
                TaskSegment(id="s2", description="Claude independent pass",
                           assigned_agent="claude", mode=mode, priority=2),
                TaskSegment(id="s3", description="Merge and reconcile results",
                           assigned_agent="claude", mode=mode, priority=4),
            ]
        else:  # HANDOVER
            segments = [
                TaskSegment(id="s1", description="Codex first pass",
                           assigned_agent="codex", mode=mode, priority=1),
                TaskSegment(id="s2", description="Claude second pass",
                           assigned_agent="claude", mode=mode, priority=2),
                TaskSegment(id="s3", description="Codex final polish",
                           assigned_agent="codex", mode=mode, priority=3),
            ]

        # Estimate duration: 5s per segment
        est_ms = len(segments) * 5000.0

        return DecomposedTask(
            original_prompt=prompt,
            segments=segments,
            mode=mode,
            estimated_duration_ms=est_ms,
        )


# ── Collaboration workflow ────────────────────────────────────────────────────

@dataclass
class WorkflowResult:
    task: str
    mode: CollaborationMode
    output: str
    segments_completed: int
    total_segments: int
    duration_ms: float
    success: bool
    merged_output: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "mode": self.mode.value,
            "output": self.output,
            "segments_completed": self.segments_completed,
            "total_segments": self.total_segments,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "merged_output": self.merged_output,
        }


class CollaborationWorkflow:
    """
    Executes a dual-mode collaboration workflow.

    Simulates agent contributions (in real usage, hooks into actual model providers).
    """

    def __init__(self) -> None:
        self._mode_selector = ModeSelector()
        self._completed: list[WorkflowResult] = []

    def execute(self, prompt: str, preferred_mode: CollaborationMode | None = None) -> WorkflowResult:
        """Execute collaboration workflow for a prompt."""
        start = time.time()

        # Select mode
        mode = preferred_mode or self._mode_selector.select_mode(prompt)

        # Decompose
        task = self._mode_selector.decompose_task(prompt, mode)

        # Simulate execution (each segment takes ~2s)
        completed = 0
        outputs = []
        for seg in task.segments:
            # Simulate segment execution
            outputs.append(f"[{seg.assigned_agent.upper()}] {seg.description}")
            seg.status = "done"
            seg.output = outputs[-1]
            completed += 1

        # Merge output
        merged = "\n".join(outputs)

        duration = (time.time() - start) * 1000

        result = WorkflowResult(
            task=prompt[:50],
            mode=mode,
            output=merged,
            segments_completed=completed,
            total_segments=len(task.segments),
            duration_ms=duration,
            success=(completed == len(task.segments)),
            merged_output=merged,
        )

        self._completed.append(result)
        return result

    def results(self) -> list[WorkflowResult]:
        return list(self._completed)

    def stats(self) -> dict[str, Any]:
        if not self._completed:
            return {"total": 0, "by_mode": {}, "avg_duration_ms": 0.0}

        by_mode: dict[str, int] = {}
        total_dur = 0.0
        for r in self._completed:
            by_mode[r.mode.value] = by_mode.get(r.mode.value, 0) + 1
            total_dur += r.duration_ms

        return {
            "total": len(self._completed),
            "by_mode": by_mode,
            "avg_duration_ms": round(total_dur / len(self._completed), 2),
            "success_rate": round(sum(1 for r in self._completed if r.success) / len(self._completed), 2),
        }


# ── Template library (backward compatibility) ──────────────────────────────────

def feature_template() -> list[DualModeTask]:
    return [
        DualModeTask(claude_role="architect", codex_role="coder"),
        DualModeTask(claude_role="tester", codex_role="reviewer"),
    ]


# ── Convenience API ───────────────────────────────────────────────────────────

_workflow = CollaborationWorkflow()


def collaborate(prompt: str, mode: CollaborationMode | None = None) -> WorkflowResult:
    return _workflow.execute(prompt, mode)


def decompose(prompt: str, mode: CollaborationMode | None = None) -> DecomposedTask:
    selector = ModeSelector()
    m = mode or selector.select_mode(prompt)
    return selector.decompose_task(prompt, m)


def collaboration_stats() -> dict[str, Any]:
    return _workflow.stats()