"""Attention mechanisms (pure Python fallback, no torch required)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np


DEFAULT_DIMS = 128
NUM_HEADS = 4


def _to_tensor(x: list[float] | np.ndarray) -> np.ndarray:
    if isinstance(x, np.ndarray):
        return x
    return np.array(x, dtype=np.float32)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max())
    return e / (e.sum() + 1e-9)


@dataclass
class AttentionOutput:
    context: list[float]
    attention_weights: list[list[float]]
    inference_ms: float


def _scaled_dot(q: np.ndarray, k: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    scale = 1.0 / math.sqrt(k.shape[1])
    scores = q @ k.T * scale
    weights = _softmax(scores)
    context = weights @ v
    return context, weights


class ScaledDotProductAttention:
    def __init__(self, d_model: int = DEFAULT_DIMS) -> None:
        self.d_model = d_model
        self.scale = 1.0 / math.sqrt(d_model)

    def forward_single(self, query: list[float], key: list[list[float]], value: list[list[float]]) -> tuple[list[float], list[float]]:
        start = time.perf_counter()
        q_t = _to_tensor(query).reshape(1, 1, -1)
        k_t = _to_tensor(key).reshape(1, len(key), -1)
        v_t = _to_tensor(value).reshape(1, len(value), -1)
        context, weights = _scaled_dot(q_t.squeeze(0), k_t.squeeze(0), v_t.squeeze(0))
        return context.tolist(), weights.tolist()


class MultiHeadAttention:
    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        if d_model % num_heads != 0:
            num_heads = 4
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.d_model = d_model
        self.scale = 1.0 / math.sqrt(self.head_dim)

    def forward_vector(self, query: list[float], context_vectors: list[list[float]]) -> tuple[list[float], list[float]]:
        start = time.perf_counter()
        q = _to_tensor(query).reshape(1, 1, -1)
        c = np.array(context_vectors, dtype=np.float32).reshape(1, len(context_vectors), -1)
        d_k = q.shape[-1]
        scores = (q @ c.transpose(0, 2, 1)) * self.scale / d_k
        weights = _softmax(scores.squeeze(0))
        output = (weights @ c.squeeze(0)).squeeze(0)
        return output.tolist(), weights.tolist()


@dataclass
class CrossAttentionResult:
    output_vector: list[float]
    attention_weights: list[list[float]]
    top_positions: list[int]
    inference_ms: float


class CrossAttention:
    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        self.mha = MultiHeadAttention(d_model, num_heads)

    def attend(self, query: list[float], memory_keys: list[list[float]], memory_values: list[list[float]]) -> CrossAttentionResult:
        start = time.perf_counter()
        output, weights = self.mha.forward_vector(query, memory_keys)
        avg_weights = np.mean(np.array(weights), axis=0).tolist() if weights else []
        top_positions = sorted(range(len(avg_weights)), key=lambda i: avg_weights[i], reverse=True)[:3] if avg_weights else []
        return CrossAttentionResult(output, [weights], top_positions, (time.perf_counter() - start) * 1000)


class TaskCrossEncoder:
    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        self.d_model = d_model
        self.cross_attn = CrossAttention(d_model, num_heads)

    def encode(self, task: str, context_docs: list[str]) -> 'MemoryBank':
        def _encode_text(text: str) -> np.ndarray:
            tokens = text.lower().split()
            vec = np.zeros(d_model, dtype=np.float32)
            for i, tok in enumerate(tokens[:64]):
                h = abs(hash(tok)) % d_model
                vec[h] += 1
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec

        d_model = self.d_model
        keys, values, metadata = [], [], []
        task_vec = _encode_text(task)
        keys.append(task_vec.tolist())
        values.append(task_vec.tolist())
        metadata.append({'type': 'task', 'text': task[:100]})
        for doc in context_docs:
            doc_vec = _encode_text(doc)
            keys.append(doc_vec.tolist())
            values.append(doc_vec.tolist())
            metadata.append({'type': 'context', 'text': doc[:100]})
        return MemoryBank(keys=keys, values=values, metadata=metadata)

    def route(self, task: str, context_docs: list[str], query_vector: list[float]) -> CrossAttentionResult:
        bank = self.encode(task, context_docs)
        return self.cross_attn.attend(query_vector, bank.keys, bank.values)


@dataclass
class MemoryBank:
    keys: list[list[float]]
    values: list[list[float]]
    metadata: list[dict[str, Any]]


class AgentAttentionLayer:
    def __init__(self, num_agents: int = 8, state_dim: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        self.num_agents = num_agents
        self.state_dim = state_dim
        self.mha = MultiHeadAttention(state_dim, num_heads)

    def fuse_states(self, agent_states: list[list[float]]) -> list[list[float]]:
        states = np.array(agent_states, dtype=np.float32).reshape(1, len(agent_states), -1)
        c = states.squeeze(0)
        scores = (c @ c.T) * self.mha.scale
        weights = _softmax(scores)
        fused = weights @ c
        return fused.tolist()


def scaled_dot_product(query: list[float], key: list[list[float]], value: list[list[float]]) -> tuple[list[float], list[float]]:
    return ScaledDotProductAttention(d_model=len(query)).forward_single(query, key, value)


def cross_attend(query: list[float], keys: list[list[float]], values: list[list[float]], d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> CrossAttentionResult:
    return CrossAttention(d_model=d_model, num_heads=num_heads).attend(query, keys, values)


def create_memory_bank(task: str, context_docs: list[str]) -> MemoryBank:
    return TaskCrossEncoder().encode(task, context_docs)
