"""Neural network components for agent decision-making (pure Python fallback)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class NeuralRouter:
    state_dim: int = 128
    num_actions: int = 4
    _weights: np.ndarray | None = None

    def __post_init__(self) -> None:
        self._weights = np.random.randn(self.state_dim, self.num_actions) * 0.01

    def score(self, state: list[float], action: int) -> float:
        if self._weights is None:
            return 0.0
        s = np.array(state, dtype=np.float32)
        return float(np.dot(s, self._weights[:, action % self.num_actions]))

    def route(self, state: list[float]) -> int:
        scores = [self.score(state, a) for a in range(self.num_actions)]
        return int(np.argmax(scores))


@dataclass
class PolicyNetwork:
    state_dim: int = 128
    hidden_dim: int = 256
    num_actions: int = 4

    def __post_init__(self) -> None:
        self.w1 = np.random.randn(self.state_dim, self.hidden_dim) * 0.01
        self.b1 = np.zeros(self.hidden_dim)
        self.w2 = np.random.randn(self.hidden_dim, self.num_actions) * 0.01
        self.b2 = np.zeros(self.num_actions)

    def forward(self, state: np.ndarray) -> np.ndarray:
        h = np.tanh(state @ self.w1 + self.b1)
        return h @ self.w2 + self.b2

    def get_action_scores(self, state: list[float]) -> np.ndarray:
        return self.forward(np.array(state, dtype=np.float32).reshape(1, -1)).flatten()

    def best_action(self, state: list[float]) -> int:
        return int(np.argmax(self.get_action_scores(state)))


@dataclass
class AttentionPool:
    num_agents: int = 8
    state_dim: int = 128

    def attend(self, agent_states: list[list[float]], query: list[float]) -> list[float]:
        states = np.array(agent_states, dtype=np.float32)
        q = np.array(query, dtype=np.float32)
        scores = (states @ q) / math.sqrt(self.state_dim)
        weights = self._softmax(scores)
        return (weights @ states).tolist()

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        e = np.exp(x - x.max())
        return e / (e.sum() + 1e-9)


@dataclass
class AgentStateEncoder:
    state_dim: int = 128

    def encode(self, agent_id: str, task_history: list[str], context: dict[str, Any]) -> list[float]:
        tokens = ' '.join(task_history).lower().split()
        vec = np.zeros(self.state_dim, dtype=np.float32)
        for tok in tokens[:self.state_dim]:
            h = abs(hash(tok)) % self.state_dim
            vec[h] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()


@dataclass
class NeuralRouterResult:
    routed_agent: int
    confidence: float
    reasoning: str
    latency_ms: float


def create_neural_router(num_agents: int = 8, state_dim: int = 128) -> NeuralRouter:
    return NeuralRouter(state_dim=state_dim, num_actions=num_agents)


def create_policy_network(state_dim: int = 128, hidden_dim: int = 256, num_actions: int = 4) -> PolicyNetwork:
    return PolicyNetwork(state_dim=state_dim, hidden_dim=hidden_dim, num_actions=num_actions)


def create_attention_pool(num_agents: int = 8, state_dim: int = 128) -> AttentionPool:
    return AttentionPool(num_agents=num_agents, state_dim=state_dim)
