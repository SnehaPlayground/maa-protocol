"""
Learning module — full RL suite from original maa_protocol/rl.py
plus enhanced self-learning components.

Provides:
- QLearningAgent (tabular Q-learning with epsilon-greedy)
- PolicyGradientAgent (REINFORCE policy gradient)
- SARSAAgent (on-policy TD control)
- RewardShaper (potential-based reward shaping)
- RLRunner (training loop)
- ReasoningBank (persistent reasoning pattern store)
- EWC (Elastic Weight Consolidation for catastrophic forgetting prevention)
"""

from __future__ import annotations

import math
import random
import time as _time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    np = None  # type: ignore
    _HAS_NUMPY = False


# ── Constants ─────────────────────────────────────────────────────────────────

DEFAULT_LEARNING_RATE = 0.1
DEFAULT_GAMMA = 0.9
DEFAULT_EPSILON = 1.0
EPSILON_DECAY = 0.99
MIN_EPSILON = 0.05
EPISODE_BATCH = 10


# ── Dataclasses ───────────────────────────────────────────────────────────────


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


# ── RewardShaper ──────────────────────────────────────────────────────────────


class RewardShaper:
    """
    Potential-based reward shaping.

    φ(s) = shaping_factor * potential(s)
    shaped_reward = r(s,a,s') + γ * φ(s') - φ(s)
    """

    def __init__(
        self,
        potential_fn: callable = lambda s: 0.0,
        gamma: float = DEFAULT_GAMMA,
        shaping_factor: float = 0.1,
    ) -> None:
        self.potential_fn = potential_fn
        self.gamma = gamma
        self.shaping_factor = shaping_factor
        self._potential_cache: dict[str, float] = {}

    def potential(self, state: str) -> float:
        if state not in self._potential_cache:
            self._potential_cache[state] = self.potential_fn(state)
        return self._potential_cache[state]

    def shape(
        self,
        state: str,
        action: str,
        reward: float,
        next_state: str,
    ) -> float:
        phi_s = self.potential(state)
        phi_sp = self.potential(next_state)
        shaped = reward + self.gamma * phi_sp - phi_s
        return shaped * self.shaping_factor + reward

    def update_cache(self, state: str, potential: float) -> None:
        self._potential_cache[state] = potential

    def clear_cache(self) -> None:
        self._potential_cache.clear()


# ── QLearningAgent ────────────────────────────────────────────────────────────


class QLearningAgent:
    """
    Tabular Q-learning agent with epsilon-greedy exploration.

    Suitable for discrete state/action spaces (routing decisions, task selection).
    """

    def __init__(
        self,
        actions: list[str],
        learning_rate: float = DEFAULT_LEARNING_RATE,
        gamma: float = DEFAULT_GAMMA,
        epsilon: float = DEFAULT_EPSILON,
        epsilon_decay: float = EPSILON_DECAY,
        min_epsilon: float = MIN_EPSILON,
    ) -> None:
        self.actions = actions
        self.lr = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.min_epsilon = min_epsilon
        self.q_table: dict[str, dict[str, float]] = {}
        self._episode_rewards: list[float] = []

    def _get_q(self, state: str, action: str) -> float:
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        return self.q_table[state][action]

    def select_action(self, state: str) -> str:
        if random.random() < self.epsilon:
            return random.choice(self.actions)
        q_vals = [self._get_q(state, a) for a in self.actions]
        max_q = max(q_vals)
        candidates = [a for a, q in zip(self.actions, q_vals) if q == max_q]
        return random.choice(candidates)

    def update(
        self,
        state: str,
        action: str,
        reward: float,
        next_state: str,
        done: bool = False,
    ) -> float:
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        if next_state not in self.q_table:
            self.q_table[next_state] = {a: 0.0 for a in self.actions}

        q_sa = self.q_table[state][action]

        if done:
            target = reward
        else:
            max_next_q = max(self.q_table[next_state].values())
            target = reward + self.gamma * max_next_q

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
        return {
            "states": len(self.q_table),
            "epsilon": round(self.epsilon, 4),
            "avg_reward": round(sum(self._episode_rewards) / max(1, len(self._episode_rewards)), 4),
        }

    def save(self, path: Path) -> None:
        import json
        data = {
            "q_table": self.q_table,
            "epsilon": self.epsilon,
            "lr": self.lr,
            "gamma": self.gamma,
        }
        path.write_text(json.dumps(data))

    def load(self, path: Path) -> None:
        import json
        data = json.loads(path.read_text())
        self.q_table = data["q_table"]
        self.epsilon = data["epsilon"]


# ── PolicyGradientAgent ───────────────────────────────────────────────────────


class PolicyGradientAgent:
    """
    REINFORCE policy gradient agent.

    Learns a probability distribution over actions given states.
    Requires numpy.
    """

    def __init__(
        self,
        state_dim: int = 128,
        actions: list[str] | None = None,
        learning_rate: float = 0.01,
        gamma: float = DEFAULT_GAMMA,
    ) -> None:
        if not _HAS_NUMPY:
            raise ImportError("numpy required for PolicyGradientAgent")
        self.state_dim = state_dim
        self.actions = actions or ["action_0", "action_1", "action_2"]
        self.num_actions = len(self.actions)
        self.lr = learning_rate
        self.gamma = gamma

        self.weights = np.random.randn(state_dim, self.num_actions) * 0.01  # type: ignore
        self.bias = np.zeros(self.num_actions)  # type: ignore

        self._trajectory: list[Transition] = []
        self._log_probs: list[float] = []

    def _scores(self, state: np.ndarray) -> np.ndarray:
        return state @ self.weights + self.bias

    def get_action_probs(self, state: np.ndarray) -> np.ndarray:
        s = np.array(state, dtype=np.float32).reshape(1, -1)
        scores = self._scores(s).flatten()
        scores -= scores.max()
        exp = np.exp(scores)
        return exp / exp.sum()

    def select_action(self, state: np.ndarray) -> tuple[str, float]:
        probs = self.get_action_probs(state)
        action_idx = np.random.choice(self.num_actions, p=probs)
        log_prob = math.log(probs[action_idx] + 1e-8)
        self._log_probs.append(log_prob)
        return self.actions[action_idx], log_prob

    def store_transition(self, transition: Transition) -> None:
        self._trajectory.append(transition)

    def update(self, baseline: float = 0.0) -> dict[str, float]:
        if not self._trajectory:
            return {"policy_loss": 0.0, "avg_return": 0.0}

        returns = []
        G = 0.0
        for t in reversed(range(len(self._trajectory))):
            G = self._trajectory[t].reward + self.gamma * G
            returns.insert(0, G)

        returns = np.array(returns, dtype=np.float32)
        if len(returns) > 1:
            returns = (returns - returns.mean()) / (returns.std() + 1e-8)

        total_loss = 0.0
        for t, (tr, lp) in enumerate(zip(self._trajectory, self._log_probs)):
            advantage = returns[t] - baseline
            probs_t = self.get_action_probs(np.array(tr.state, dtype=np.float32).reshape(1, -1)).flatten()
            grad = np.zeros_like(self.weights)
            for a in range(self.num_actions):
                label = 1.0 if a == self.actions.index(tr.action) else 0.0
                grad[:, a] = (label - probs_t[a]) * np.array(tr.state, dtype=np.float32)
            self.weights += self.lr * advantage * grad
            self.bias += self.lr * advantage * (probs_t - (np.arange(self.num_actions) == self.actions.index(tr.action)).astype(float))
            total_loss += -lp * advantage

        avg_return = float(returns.mean()) if len(returns) > 0 else 0.0
        self._trajectory.clear()
        self._log_probs.clear()
        return {"policy_loss": total_loss / len(returns), "avg_return": avg_return}

    def reset_trajectory(self) -> None:
        self._trajectory.clear()
        self._log_probs.clear()

    def get_stats(self) -> dict[str, Any]:
        return {
            "state_dim": self.state_dim,
            "num_actions": self.num_actions,
            "lr": self.lr,
            "trajectory_len": len(self._trajectory),
        }


# ── SARSAAgent ────────────────────────────────────────────────────────────────


class SARSAAgent:
    """
    On-policy TD control (SARSA).

    Q(s,a) += lr * [r + gamma * Q(s',a') - Q(s,a)]
    """

    def __init__(
        self,
        actions: list[str],
        learning_rate: float = DEFAULT_LEARNING_RATE,
        gamma: float = DEFAULT_GAMMA,
        epsilon: float = DEFAULT_EPSILON,
    ) -> None:
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

    def step(
        self,
        state: str,
        action: str,
        reward: float,
        next_state: str,
        next_action: str,
        done: bool = False,
    ) -> float:
        if state not in self.q_table:
            self.q_table[state] = {a: 0.0 for a in self.actions}
        if next_state not in self.q_table:
            self.q_table[next_state] = {a: 0.0 for a in self.actions}

        q_sa = self.q_table[state][action]

        if done:
            target = reward
        else:
            q_sa_next = self.q_table[next_state][next_action]
            target = reward + self.gamma * q_sa_next

        td_error = target - q_sa
        self.q_table[state][action] = q_sa + self.lr * td_error
        self._current_action = next_action
        return td_error

    def decay_epsilon(self, factor: float = 0.99) -> None:
        self.epsilon = max(MIN_EPSILON, self.epsilon * factor)


# ── RLEnvironment (abstract) ──────────────────────────────────────────────────


class RLEnvironment:
    def __init__(self) -> None:
        self._state: str = "init"

    def reset(self) -> str:
        self._state = "init"
        return self._state

    def step(self, state: str, action: str) -> tuple[str, float, bool]:
        next_state, reward, done = self._transition(state, action)
        self._state = next_state
        return next_state, reward, done

    def _transition(self, state: str, action: str) -> tuple[str, float, bool]:
        return state, 0.0, True


class RoutingEnv(RLEnvironment):
    """
    Toy routing environment.

    States: "idle", "task_pending", "high_load", "done"
    Actions: "route_coordinator", "route_researcher", "route_coder", "defer"
    """

    def _transition(self, state: str, action: str) -> tuple[str, float, bool]:
        if state == "init":
            return "task_pending", 0.0, False

        if state == "task_pending":
            if action in ["route_coordinator", "route_researcher", "route_coder"]:
                return "idle", 1.0, False
            if action == "defer":
                return "high_load", -0.5, False
            return "idle", -1.0, False

        if state == "high_load":
            if action == "defer":
                return "done", 0.5, True
            return "done", -1.0, True

        return "done", 0.0, True


# ── RLRunner ──────────────────────────────────────────────────────────────────


class RLRunner:
    def __init__(
        self,
        agent: QLearningAgent | SARSAAgent,
        env: RLEnvironment,
        config: RLConfig | None = None,
    ) -> None:
        self.agent = agent
        self.env = env
        self.config = config or RLConfig()

    def run_episode(self) -> tuple[float, int]:
        state = self.env.reset()
        total_reward = 0.0
        steps = 0
        done = False

        if isinstance(self.agent, QLearningAgent):
            while not done:
                action = self.agent.select_action(state)
                next_state, reward, done = self.env.step(state, action)
                self.agent.update(state, action, reward, next_state, done)
                state = next_state
                total_reward += reward
                steps += 1
            self.agent.decay_epsilon()

        elif isinstance(self.agent, SARSAAgent):
            action = self.agent.start(state)
            while not done:
                next_state, reward, done = self.env.step(state, action)
                next_action = self.agent.select_action(next_state)
                self.agent.step(state, action, reward, next_state, next_action, done)
                state = next_state
                action = next_action
                total_reward += reward
                steps += 1
            self.agent.decay_epsilon()

        return total_reward, steps

    def train(self, episodes: int | None = None) -> RLResult:
        start = _time.perf_counter()
        ep_count = episodes or self.config.episodes
        rewards = []

        for _ in range(ep_count):
            r, _ = self.run_episode()
            rewards.append(r)

        ms = (_time.perf_counter() - start) * 1000
        return RLResult(
            total_reward=sum(rewards),
            episodes_completed=ep_count,
            final_epsilon=self.agent.epsilon,
            q_table_size=len(self.agent.q_table) if hasattr(self.agent, "q_table") else 0,
            training_time_ms=ms,
        )


# ── Convenience factories ──────────────────────────────────────────────────────


def create_q_agent(actions: list[str]) -> QLearningAgent:
    return QLearningAgent(actions=actions)


def create_policy_gradient(state_dim: int, actions: list[str]) -> PolicyGradientAgent:
    return PolicyGradientAgent(state_dim=state_dim, actions=actions)


def create_sarsa(actions: list[str]) -> SARSAAgent:
    return SARSAAgent(actions=actions)


def create_routing_env() -> RoutingEnv:
    return RoutingEnv()