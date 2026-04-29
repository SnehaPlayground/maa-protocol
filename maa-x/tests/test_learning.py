"""Tests for maa_x learning module."""

import pytest
from maa_x.learning import (
    QLearningAgent,
    SARSAAgent,
    RLConfig,
    RLRunner,
    RewardShaper,
    RoutingEnv,
    create_q_agent,
    create_routing_env,
)


def test_q_agent_epsilon_greedy():
    agent = QLearningAgent(actions=["a", "b", "c"])
    action = agent.select_action("state_1")
    assert action in ["a", "b", "c"]


def test_q_agent_update():
    agent = QLearningAgent(actions=["a", "b"])
    td = agent.update("s1", "a", 1.0, "s2", done=False)
    # Second update to same transition
    td2 = agent.update("s1", "a", 0.5, "s2", done=False)
    assert td2 != 0.0  # learning happened


def test_q_agent_epsilon_decay():
    agent = QLearningAgent(actions=["a", "b"], epsilon=1.0, epsilon_decay=0.5, min_epsilon=0.1)
    initial_eps = agent.epsilon
    agent.decay_epsilon()
    assert agent.epsilon < initial_eps
    for _ in range(10):
        agent.decay_epsilon()
    assert agent.epsilon == 0.1  # floor


def test_create_q_agent():
    agent = create_q_agent(["left", "right"])
    assert len(agent.actions) == 2


def test_reward_shaper():
    shaper = RewardShaper(potential_fn=lambda s: 1.0 if "done" in s else 0.0, shaping_factor=1.0)
    shaped = shaper.shape("start", "go", 0.0, "done")
    assert shaped != 0.0  # shaped reward differs from raw


def test_routing_env():
    env = create_routing_env()
    state = env.reset()
    # reset() returns initial state "init"
    assert state == "init"
    next_state, reward, done = env.step(state, "route_coordinator")
    # after first step: init -> task_pending
    assert next_state == "task_pending"


def test_sarsa_agent():
    agent = SARSAAgent(actions=["up", "down"])
    action = agent.select_action("start")
    assert action in ["up", "down"]
    td = agent.step("start", action, 1.0, "mid", "down", done=False)
    assert isinstance(td, float)


def test_rl_runner_episode():
    agent = QLearningAgent(actions=["a", "b"])
    env = RoutingEnv()
    runner = RLRunner(agent, env)
    reward, steps = runner.run_episode()
    assert isinstance(reward, float)
    assert steps > 0


def test_rl_runner_train():
    agent = QLearningAgent(actions=["a", "b"])
    env = RoutingEnv()
    runner = RLRunner(agent, env, RLConfig(episodes=5))
    result = runner.train()
    assert result.episodes_completed == 5
    assert result.training_time_ms > 0