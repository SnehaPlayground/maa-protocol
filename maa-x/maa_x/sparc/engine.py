"""SPARC module — Structured Planning with Active Reflection and Consensus.

SPARC is a TDD-inspired agent execution methodology:
Plan → Act → Sense → Reflect → Correct → Coordinate
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SPARCStep:
    phase: str          # plan | act | sense | reflect | correct | coordinate
    action: str
    observation: str | None = None
    result: Any = None
    confidence: float = 1.0


@dataclass
class SPARCExecution:
    task: str
    steps: list[SPARCStep] = field(default_factory=list)
    outcome: str | None = None
    consensus_reached: bool = False

    def add_step(self, phase: str, action: str, observation: str | None = None) -> None:
        self.steps.append(SPARCStep(phase=phase, action=action, observation=observation))


class SPARCEngine:
    """
    SPARC execution engine.

    Drives a task through the SPARC phases: Plan → Act → Sense → Reflect → Correct → Coordinate.

    Parameters
    ----------
    max_iterations
        Safety cap on SPARC cycles.
    confidence_threshold
        Minimum confidence to accept result without correction.
    """

    def __init__(
        self,
        max_iterations: int = 10,
        confidence_threshold: float = 0.85,
    ) -> None:
        self.max_iterations = max_iterations
        self.confidence_threshold = confidence_threshold
        self._execution: SPARCExecution | None = None

    def execute(self, task: str, executor: Any = None) -> SPARCExecution:
        """
        Run SPARC cycle on a task.

        Parameters
        ----------
        task
            Task description or instruction.
        executor
            Callable that executes an action and returns (observation, result, confidence).
            Signature: ``def execute(action: str) -> (observation: str, result: Any, confidence: float)``
        """
        self._execution = SPARCExecution(task=task)
        iteration = 0

        # Plan
        self._execution.add_step("plan", f"analyze: {task[:80]}")
        if executor:
            obs, result, conf = executor(f"analyze: {task[:80]}")
            self._execution.add_step("act", f"analyze: {task[:80]}", obs)
            self._execution.steps[-1].result = result
            self._execution.steps[-1].confidence = conf
        else:
            self._execution.add_step("act", f"analyze: {task[:80]}", "simulated: no-op")
            self._execution.steps[-1].confidence = 0.5

        # Sense / Reflect loop
        while iteration < self.max_iterations:
            iteration += 1

            if executor:
                obs, result, conf = executor(f"execute_iteration_{iteration}")
                self._execution.add_step("sense", f"iteration_{iteration}", obs)
                self._execution.steps[-1].result = result
                self._execution.steps[-1].confidence = conf

                if conf >= self.confidence_threshold:
                    self._execution.add_step("reflect", f"confidence_met_{conf:.2f}")
                    self._execution.outcome = "success"
                    break
                else:
                    self._execution.add_step("correct", f"confidence_low_retry_{iteration}")
            else:
                self._execution.add_step("sense", f"iteration_{iteration}", "simulated")
                self._execution.add_step("reflect", f"confidence_0.8")
                self._execution.outcome = "simulated"
                break

        self._execution.add_step("coordinate", "finalize")
        return self._execution

    @property
    def execution(self) -> SPARCExecution | None:
        return self._execution


def run_sparc(task: str, executor: Any = None) -> SPARCExecution:
    return SPARCEngine().execute(task, executor)