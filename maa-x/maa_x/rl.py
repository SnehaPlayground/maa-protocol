"""RL algorithms: Q-learning, policy gradient, SARSA, reward shaping."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE = Path('/root/.openclaw/workspace')
RL_CACHE = WORKSPACE / 'maa_protocol' / 'rl_cache'
RL_CACHE.mkdir(parents=True, exist_ok=True)

DEFAULT_LEARNING_RATE = 0.1
DEFAULT_GAMMA = 0.9
DEFAULT_EPSILON = 1.0
EPSILON_DECAY = 0.99
MIN_EPSILON = 0.05


@dataclass
class RLConfig:
    learning_rate: float = DEFAULT_LEARNING_RATE
    gamma: float = DEFAULT_GAMMA
    epsilon: float = DEFAULT_EPSILON
    epsilon_decay: float = EPSILON_DECAY
    min_epsilon: float = MIN_EPSILON
    episodes: int = 100


@dataclass
class RLResult:
    total_reward: float
    episodes_completed: int
    final_epsilon: float
    q_table_size: int
    training_time_ms: float


@dataclass
class Transition:
    state: str
    action: str
    reward: float
    next_state: str
    done: bool


class RewardShaper:
    def __init__(self, potential_fn: callable = lambda s: 0.0, gamma: float = DEFAULT_GAMMA, shaping_factor: float = 0.1) -> None:
        self.potential_fn = potential_fn
        self.gamma = gamma
        self.shaping_factor = shaping_factor
        self._cache: dict[str, float] = {}

    def potential(self, state: str) -> float:
        if state not in self._cache:
            self._cache[state] = self.potential_fn(state)
        return self._cache[state]

    def shape(self, state: str, action: str, reward: float, next_state: str) -> float:
        phi_s = self.potential(state)
        phi_sp = self.potential(next_state)
        shaped = reward + self.gamma * phi_sp - phi_s
        return shaped * self.shaping_factor + reward

    def clear_cache(self) -> None:
        self._cache.clear()


class QLearningAgent:
    def __init__(self, actions: list[str], learning_rate: float = DEFAULT_LEARNING_RATE, gamma: float = DEFAULT_GAMMA, epsilon: float = DEFAULT_EPSILON, epsilon_decay: float = EPSILON_DECAY, min_epsilon: float = MIN_EPSILON) -> None:
        self.actions = actions
        self.lr = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = min_epsilon
        self.q_table: dict[str, dict[str, float]] = {}

    def select_action(self, state: str) -> str:
        if random.random() < self.epsilon:
            return random.choice(self.actions)
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        q_vals = [self.q_table[state][a] for a in self.actions]
        max_q = max(q_vals)
        return random.choice([a for a, q in zip(self.actions, q_vals) if q == max_q])

    def update(self, state: str, action: str, reward: float, next_state: str, done: bool = False) -> float:
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        if next_state not in self.q_table:
            self.q_table[next_state] = {a: 0.0 for a in self.actions}
        q_sa = self.q_table[state][action]
        target = reward if done else reward + self.gamma * max(self.q_table[next_state].values())
        td_error = target - q_sa
        self.q_table[state][action] = q_sa + self.lr * td_error
        return td_error

    def decay_epsilon(self) -> None:
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

    def get_value(self, state: str) -> float:
        if state not in self.q_table:
            return 0.0
        return max(self.q_table[state].values())

    def stats(self) -> dict[str, Any]:
        return {'states': len(self.q_table), 'epsilon': round(self.epsilon, 4)}


class PolicyGradientAgent:
    def __init__(self, state_dim: int = 128, actions: list[str] | None = None, learning_rate: float = 0.01, gamma: float = DEFAULT_GAMMA) -> None:
        self.state_dim = state_dim
        self.actions = actions or ['action_0', 'action_1', 'action_2']
        self.num_actions = len(self.actions)
        self.lr = learning_rate
        self.gamma = gamma
        self.weights = np.random.randn(state_dim, self.num_actions) * 0.01
        self.bias = np.zeros(self.num_actions)
        self._trajectory: list[Transition] = []
        self._log_probs: list[float] = []

    def _scores(self, state: np.ndarray) -> np.ndarray:
        return state @ self.weights + self.bias

    def get_action_probs(self, state: np.ndarray) -> np.ndarray:
        s = np.array(state, dtype=np.float32).reshape(1, -1)
        scores = self._scores(s).flatten()
        scores -= scores.max()
        exp = np.exp(scores)
        return exp / (exp.sum() + 1e-8)

    def select_action(self, state: np.ndarray) -> tuple[str, float]:
        probs = self.get_action_probs(state)
        action_idx = np.random.choice(self.num_actions, p=probs)
        return self.actions[action_idx], math.log(probs[action_idx] + 1e-8)

    def store_transition(self, t: Transition) -> None:
        self._trajectory.append(t)

    def update(self, baseline: float = 0.0) -> dict[str, float]:
        if not self._trajectory:
            return {'policy_loss': 0.0, 'avg_return': 0.0}
        returns = []
        G = 0.0
        for t in reversed(range(len(self._trajectory))):
            G = self._trajectory[t].reward + self.gamma * G
            returns.insert(0, G)
        returns = np.array(returns, dtype=np.float32)
        if len(returns) > 1:
            returns = (returns - returns.mean()) / (returns.std() + 1e-8)
        total_loss = 0.0
        for t, lp in zip(self._trajectory, self._log_probs):
            advantage = returns[len(self._trajectory) - 1 - self._trajectory.index(t)] - baseline
            probs_t = self.get_action_probs(np.array(t.state, dtype=np.float32).reshape(1, -1)).flatten()
            grad = np.zeros_like(self.weights)
            for a in range(self.num_actions):
                label = 1.0 if a == self.actions.index(t.action) else 0.0
                grad[:, a] = (label - probs_t[a]) * np.array(t.state, dtype=np.float32)
            self.weights += self.lr * advantage * grad
            total_loss += -lp * advantage
        avg_return = float(returns.mean()) if len(returns) > 0 else 0.0
        self._trajectory.clear()
        self._log_probs.clear()
        return {'policy_loss': total_loss / max(1, len(returns)), 'avg_return': avg_return}


class SARSAAgent:
    def __init__(self, actions: list[str], learning_rate: float = DEFAULT_LEARNING_RATE, gamma: float = DEFAULT_GAMMA, epsilon: float = DEFAULT_EPSILON) -> None:
        self.actions = actions
        self.lr = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.q_table: dict[str, dict[str, float]] = {}
        self._current_action: str | None = None

    def select_action(self, state: str, epsilon: float | None = None) -> str:
        e = epsilon if epsilon is not None else self.epsilon
        if random.random() < e:
            return random.choice(self.actions)
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        q_vals = [self.q_table[state][a] for a in self.actions]
        max_q = max(q_vals)
        return random.choice([a for a, q in zip(self.actions, q_vals) if q == max_q])

    def start(self, state: str) -> str:
        action = self.select_action(state)
        self._current_action = action
        return action

    def step(self, state: str, action: str, reward: float, next_state: str, next_action: str, done: bool = False) -> float:
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        if next_state not in self.q_table:
            self.q_table[next_state] = {a: 0.0 for a in self.actions}
        q_sa = self.q_table[state][action]
        target = reward if done else reward + self.gamma * self.q_table[next_state][next_action]
        td_error = target - q_sa
        self.q_table[state][action] = q_sa + self.lr * td_error
        self._current_action = next_action
        return td_error


class RLEnvironment:
    def __init__(self) -> None:
        self._state: str = 'init'

    def reset(self) -> str:
        self._state = 'init'
        return self._state

    def step(self, state: str, action: str) -> tuple[str, float, bool]:
        next_state, reward, done = self._transition(state, action)
        self._state = next_state
        return next_state, reward, done

    def _transition(self, state: str, action: str) -> tuple[str, float, bool]:
        return state, 0.0, True


class RoutingEnv(RLEnvironment):
    def __init__(self) -> None:
        super().__init__()

    def _transition(self, state: str, action: str) -> tuple[str, float, bool]:
        if state == 'init':
            return 'task_pending', 0.0, False
        if state == 'task_pending':
            if action in ('route_coordinator', 'route_researcher', 'route_coder'):
                return 'idle', 1.0, False
            if action == 'defer':
                return 'high_load', -0.5, False
            return 'idle', -1.0, False
        if state == 'high_load':
            return 'done', 0.5 if action == 'defer' else -1.0, True
        return 'done', 0.0, True
