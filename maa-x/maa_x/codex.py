"""Dual-mode AI collaboration (Codex + Claude orchestration)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CollaborationMode(Enum):
    REVIEW = 'review'
    CASCADE = 'cascade'
    PARALLEL = 'parallel'
    HANDOVER = 'handover'


class CodexAgentRole(Enum):
    ARCHITECT = 'architect'
    CODER = 'coder'
    REVIEWER = 'reviewer'
    TESTER = 'tester'


@dataclass
class DualModeTask:
    claude_role: str
    codex_role: str
    namespace: str = 'collaboration'
    description: str = ''


@dataclass
class TaskSegment:
    id: str
    description: str
    assigned_agent: str
    mode: CollaborationMode
    priority: int = 1
    status: str = 'pending'
    output: str | None = None
    duration_ms: float | None = None


@dataclass
class DecomposedTask:
    original_prompt: str
    segments: list[TaskSegment]
    mode: CollaborationMode
    estimated_duration_ms: float = 0.0

    def pending_count(self) -> int:
        return sum(1 for s in self.segments if s.status == 'pending')

    def done_count(self) -> int:
        return sum(1 for s in self.segments if s.status == 'done')


class ModeSelector:
    REVIEW_SIGNALS = ['implement', 'write code', 'build', 'create function', 'develop', 'write a script']
    CASCADE_SIGNALS = ['review', 'audit', 'validate', 'improve', 'refactor', 'debug', 'check for bugs']
    PARALLEL_SIGNALS = ['both', 'parallel', 'simultaneously', 'all of these']
    HANDOVER_SIGNALS = ['iterate', 'refine', 'handover', 'collaborate', 'pass back']

    def select_mode(self, prompt: str) -> CollaborationMode:
        p = prompt.lower()
        if any(s in p for s in self.CASCADE_SIGNALS):
            return CollaborationMode.CASCADE
        if any(s in p for s in self.REVIEW_SIGNALS):
            return CollaborationMode.REVIEW
        if any(s in p for s in self.PARALLEL_SIGNALS):
            return CollaborationMode.PARALLEL
        if any(s in p for s in self.HANDOVER_SIGNALS):
            return CollaborationMode.HANDOVER
        if any(w in p for w in ['code', 'function', 'class', 'script', 'api']):
            return CollaborationMode.REVIEW
        return CollaborationMode.CASCADE

    def decompose_task(self, prompt: str, mode: CollaborationMode) -> DecomposedTask:
        segments = []
        if mode == CollaborationMode.REVIEW:
            segments = [TaskSegment('claude-review', 'Review implementation plan', 'claude', mode, 2), TaskSegment('codex-impl', 'Implement code', 'codex', mode, 1), TaskSegment('claude-verify', 'Verify correctness', 'claude', mode, 3)]
        elif mode == CollaborationMode.CASCADE:
            segments = [TaskSegment('codex-draft', 'Initial draft', 'codex', mode, 1), TaskSegment('claude-review', 'Review and refine', 'claude', mode, 2)]
        elif mode == CollaborationMode.PARALLEL:
            segments = [TaskSegment('claude-track', 'Handle first track', 'claude', mode, 1), TaskSegment('codex-track', 'Handle second track', 'codex', mode, 1)]
        else:
            segments = [TaskSegment('codex-1', 'First pass', 'codex', mode, 1), TaskSegment('claude-1', 'Handoff review', 'claude', mode, 2), TaskSegment('codex-2', 'Second pass', 'codex', mode, 3)]
        return DecomposedTask(prompt, segments, mode, estimated_duration_ms=len(segments) * 1000.0)


class DualModeCoordinator:
    def __init__(self) -> None:
        self._selector = ModeSelector()
        self._tasks: dict[str, DecomposedTask] = {}

    def coordinate(self, prompt: str, mode: CollaborationMode | None = None) -> DecomposedTask:
        if mode is None:
            mode = self._selector.select_mode(prompt)
        task = self._selector.decompose_task(prompt, mode)
        self._tasks[prompt[:50]] = task
        return task

    def merge_results(self, task: DecomposedTask) -> dict[str, Any]:
        return {'merged': True, 'segments_completed': task.done_count(), 'mode': task.mode.value, 'output': '\n'.join(s.output or '' for s in task.segments)}
