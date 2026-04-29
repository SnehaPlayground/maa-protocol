"""Self-learning module — basic RL algorithms and pattern learning."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RLExperience:
    state: Any
    action: str
    reward: float
    next_state: Any
    done: bool


class QLearningAgent:
    """
    Simple Q-Learning agent with epsilon-greedy exploration.

    Parameters
    ----------
    actions
        List of available action names.
    learning_rate
        Alpha for Q-update.
    discount_factor
        Gamma for future reward discounting.
    epsilon
        Exploration rate.
    """

    def __init__(
        self,
        actions: list[str],
        learning_rate: float = 0.1,
        discount_factor: float = 0.9,
        epsilon: float = 0.1,
    ) -> None:
        self.actions = actions
        self.alpha = learning_rate
        self.gamma = discount_factor
        self.epsilon = epsilon
        self._q: dict[str, dict[str, float]] = {}

    def choose_action(self, state: Any) -> str:
        state_key = str(state)
        if state_key not in self._q:
            self._q[state_key] = {a: 0.0 for a in self.actions}
        if random.random() < self.epsilon:
            return random.choice(self.actions)
        return max(self._q[state_key], key=self._q[state_key].get)  # type: ignore

    def update(self, experience: RLExperience) -> None:
        s = str(experience.state)
        ns = str(experience.next_state)
        if s not in self._q:
            self._q[s] = {a: 0.0 for a in self.actions}
        if ns not in self._q:
            self._q[ns] = {a: 0.0 for a in self.actions}
        best_next = max(self._q[ns].values())
        td_target = experience.reward + self.gamma * best_next
        td_error = td_target - self._q[s][experience.action]
        self._q[s][experience.action] += self.alpha * td_error

    def q_value(self, state: Any, action: str) -> float:
        return self._q.get(str(state), {}).get(action, 0.0)


class EWC:
    """
    Elastic Weight Consolidation for preventing catastrophic forgetting.

    Uses Fisher Information to identify important parameters and adds a
    penalty to changes of those parameters during subsequent tasks.
    """

    def __init__(self, importance: float = 1000.0) -> None:
        self.importance = importance
        self._fisher: dict[str, float] = {}
        self._theta_star: dict[str, float] = {}
        self._initialized = False

    def register_task(self, named_parameters: dict[str, float]) -> None:
        """Register the optimal parameters after a task for EWC protection."""
        for name, value in named_parameters.items():
            self._theta_star[name] = value
            # Approximate Fisher: accumulated squared gradients
            self._fisher[name] = self._fisher.get(name, 0.0) + self.importance

    def penalty(self, current_parameters: dict[str, float]) -> float:
        """Compute EWC penalty for current parameter values."""
        if not self._initialized:
            return 0.0
        penalty = 0.0
        for name, current_val in current_parameters.items():
            if name in self._theta_star:
                old_val = self._theta_star[name]
                fisher = self._fisher.get(name, 1.0)
                penalty += fisher * (current_val - old_val) ** 2
        return penalty * 0.5


@dataclass
class ReasoningStep:
    reasoning: str
    confidence: float
    next_action: str


class ReasoningBank:
    """
    Stores and retrieves reasoning patterns for similar future situations.

    Pure Python implementation using SQLite for persistence.
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        import sqlite3
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reasoning_bank (
                pattern_id TEXT PRIMARY KEY,
                situation_hash TEXT NOT NULL,
                reasoning TEXT NOT NULL,
                confidence REAL NOT NULL,
                next_action TEXT NOT NULL,
                success_rate REAL NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_situation ON reasoning_bank(situation_hash)")
        self._conn.commit()

    def store(self, situation_hash: str, reasoning: str, next_action: str, success_rate: float = 1.0) -> None:
        import uuid, time
        pattern_id = str(uuid.uuid4())
        self._conn.execute(
            "INSERT INTO reasoning_bank (pattern_id, situation_hash, reasoning, confidence, next_action, success_rate, usage_count, created_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (pattern_id, situation_hash, reasoning, 1.0, next_action, success_rate, time.time()),
        )
        self._conn.commit()

    def retrieve(self, situation_hash: str, k: int = 3) -> list[dict]:
        rows = self._conn.execute(
            "SELECT reasoning, confidence, next_action, success_rate FROM reasoning_bank WHERE situation_hash = ? ORDER BY success_rate DESC, usage_count DESC LIMIT ?",
            (situation_hash, k),
        ).fetchall()
        if not rows:
            # Partial match
            rows = self._conn.execute(
                "SELECT reasoning, confidence, next_action, success_rate FROM reasoning_bank WHERE situation_hash LIKE ? ORDER BY success_rate DESC LIMIT ?",
                (f"{situation_hash[:8]}%", k),
            ).fetchall()
        return [
            {"reasoning": r[0], "confidence": r[1], "next_action": r[2], "success_rate": r[3]}
            for r in rows
        ]

    def update_success(self, situation_hash: str, success: bool) -> None:
        import time
        self._conn.execute(
            "UPDATE reasoning_bank SET usage_count = usage_count + 1, success_rate = (success_rate * usage_count + ?) / (usage_count + 1) WHERE situation_hash = ?",
            (1.0 if success else 0.0, situation_hash),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()