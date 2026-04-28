"""
MAA Protocol — Attention Mechanisms
======================================
Multi-head attention, scaled dot-product attention, and cross-attention
components for agent state processing and task routing.

Components:
- ScaledDotProductAttention — classic O(d^2) scaled attention
- MultiHeadAttention — multi-head self/cross attention
- CrossAttention — cross-attention between query and memory context
- TaskCrossEncoder — encode task+context into attention key-value pairs
- AgentAttentionLayer — full attention layer for agent state fusion
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DEVICE = torch.device("cpu")
DEFAULT_DIMS = 128
NUM_HEADS = 4


def to_tensor(x: list[float] | np.ndarray | torch.Tensor) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x
    return torch.tensor(x, dtype=torch.float32, device=DEVICE)


def to_numpy(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy()


@dataclass
class AttentionOutput:
    context: list[float]          # attention output vector as list
    attention_weights: list[list[float]]  # [head_idx][step_idx] per head
    inference_ms: float


# ── Scaled Dot-Product Attention ─────────────────────────────────────────────

class ScaledDotProductAttention(nn.Module):
    """
    Classic scaled dot-product attention.
    O(d) memory, O(d^2) compute per step.

    score(Q,K,V) = softmax(QK^T / sqrt(d)) * V

    Args:
        d_model: key/value/query dimension
    """

    def __init__(self, d_model: int = DEFAULT_DIMS) -> None:
        super().__init__()
        self.d_model = d_model
        self.scale = 1.0 / math.sqrt(d_model)

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor,
        value: torch.Tensor,
        mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            query: (batch, seq_q, d_model)
            key:   (batch, seq_k, d_model)
            value: (batch, seq_k, d_model)
            mask:  (batch, seq_q, seq_k) — 1 = keep, 0 = mask

        Returns:
            (context, attention_weights)
            context: (batch, seq_q, d_model)
            attention_weights: (batch, seq_q, seq_k)
        """
        scores = torch.matmul(query, key.transpose(-2, -1)) * self.scale

        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)

        attn_weights = F.softmax(scores, dim=-1)
        context = torch.matmul(attn_weights, value)
        return context, attn_weights

    def forward_single(
        self,
        query: list[float],
        key: list[list[float]],
        value: list[list[float]],
    ) -> tuple[list[float], list[float]]:
        """
        Single-query interface (no batch).

        Returns:
            (context_vector, attention_weights)
        """
        start = time.perf_counter()

        q_t = to_tensor(query).unsqueeze(0).unsqueeze(0)       # (1, 1, d)
        k_t = to_tensor(key).unsqueeze(0)                       # (1, seq_k, d)
        v_t = to_tensor(value).unsqueeze(0)                     # (1, seq_k, d)

        context_t, weights_t = self.forward(q_t, k_t, v_t)
        context = to_numpy(context_t.squeeze(0)).tolist()
        weights = to_numpy(weights_t.squeeze(0)).tolist()

        return context, weights


# ── Multi-Head Attention ──────────────────────────────────────────────────────

class MultiHeadAttention(nn.Module):
    """
    Multi-head self/cross attention.

    Splits d_model into num_heads head_dim = d_model // num_heads.
    Each head attends independently then outputs are concatenated and projected.

    Args:
        d_model: total embedding dimension
        num_heads: number of attention heads (must divide d_model evenly)
        dropout: attention dropout rate
    """

    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS, dropout: float = 0.1) -> None:
        super().__init__()
        if d_model % num_heads != 0:
            num_heads = 4
        self.num_heads = num_heads
        self.head_dim = d_model // num_heads
        self.d_model = d_model
        self.scale = 1.0 / math.sqrt(self.head_dim)

        self.w_q = nn.Linear(d_model, d_model)
        self.w_k = nn.Linear(d_model, d_model)
        self.w_v = nn.Linear(d_model, d_model)
        self.w_o = nn.Linear(d_model, d_model)
        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        query: torch.Tensor,
        key: torch.Tensor | None = None,
        value: torch.Tensor | None = None,
        mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            query: (batch, seq_q, d_model)
            key:   (batch, seq_k, d_model) — defaults to query if None
            value: (batch, seq_k, d_model) — defaults to key if None

        Returns:
            (context_tensor, attention_weights)
        """
        if key is None:
            key = query
        if value is None:
            value = key

        batch, seq_q, _ = query.shape
        seq_k = key.shape[1]

        Q = self.w_q(query).view(batch, seq_q, self.num_heads, self.head_dim).transpose(1, 2)
        K = self.w_k(key).view(batch, seq_k, self.num_heads, self.head_dim).transpose(1, 2)
        V = self.w_v(value).view(batch, seq_k, self.num_heads, self.head_dim).transpose(1, 2)

        scores = torch.matmul(Q, K.transpose(-2, -1)) * self.scale
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
        attn = self.dropout(F.softmax(scores, dim=-1))

        context = torch.matmul(attn, V)
        context = context.transpose(1, 2).contiguous().view(batch, seq_q, self.d_model)
        context = self.w_o(context)

        # Aggregate weights across heads for inspection
        agg_weights = to_numpy(attn.mean(dim=1)).tolist()
        return context, agg_weights

    def forward_vector(
        self,
        query: list[float],
        context_vectors: list[list[float]],
    ) -> tuple[list[float], list[float]]:
        """
        Vector interface: single query against a list of context vectors.

        Returns:
            (output_vector, per-head attention weights)
        """
        start = time.perf_counter()
        q_t = to_tensor(query).unsqueeze(0).unsqueeze(0)
        c_t = to_tensor(context_vectors).unsqueeze(0)

        out_t, weights_t = self.forward(q_t, c_t, c_t)
        output = to_numpy(out_t.squeeze(0).squeeze(0)).tolist()
        # weights_t: list[list[float]] — (num_heads, seq_k), nested list from to_numpy(agg).tolist()
        # flatten to list[float] for caller
        weights: list[float] = []
        for row in weights_t:
            if isinstance(row, list):
                weights.extend(row)
            else:
                weights.append(float(row))

        return output, weights


# ── Cross-Attention ────────────────────────────────────────────────────────────

class CrossAttention(nn.Module):
    """
    Cross-attention layer: query comes from task, key/value from memory/context.
    Used for routing tasks against stored patterns and agent memory.

    Args:
        d_model: embedding dimension
        num_heads: number of attention heads
    """

    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        super().__init__()
        self.mha = MultiHeadAttention(d_model, num_heads)

    def attend(
        self,
        query: list[float],
        memory_keys: list[list[float]],
        memory_values: list[list[float]],
    ) -> CrossAttentionResult:
        """
        Run cross-attention from a single query against a memory bank.

        Returns:
            CrossAttentionResult with output, weights, top_idx
        """
        start = time.perf_counter()
        output, weights = self.mha.forward_vector(query, memory_keys)

        # weights shape: [num_heads, seq_k]; average across heads
        avg_weights = np.mean(np.array(weights), axis=0).tolist() if weights else []

        # top attention positions
        if avg_weights:
            sorted_idx = sorted(range(len(avg_weights)), key=lambda i: avg_weights[i], reverse=True)
            top_positions = sorted_idx[:3]
        else:
            top_positions = []

        ms = (time.perf_counter() - start) * 1000
        return CrossAttentionResult(
            output_vector=output,
            attention_weights=weights,
            top_positions=top_positions,
            inference_ms=ms,
        )


@dataclass
class CrossAttentionResult:
    output_vector: list[float]
    attention_weights: list[list[float]]
    top_positions: list[int]
    inference_ms: float


# ── TaskCrossEncoder ──────────────────────────────────────────────────────────

class TaskCrossEncoder:
    """
    Encode a (task, context) pair into cross-attention key-value representation.

    Produces memory bank vectors from task description + context documents,
    suitable for cross-attention routing.

    Usage:
        encoder = TaskCrossEncoder(d_model=128)
        bank = encoder.encode_task_context("market brief", ["context doc 1", "doc 2"])
        result = cross_attn.attend(query_vector, bank.keys, bank.values)
    """

    def __init__(self, d_model: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        self.d_model = d_model
        self.cross_attn = CrossAttention(d_model, num_heads)
        self.encoder = nn.Linear(d_model, d_model)

    def encode(self, task: str, context_docs: list[str]) -> MemoryBank:
        """
        Encode task + context into a MemoryBank for cross-attention.

        Returns:
            MemoryBank with keys, values, metadata
        """
        # Simple bag-of-words encoding (replace with learned encoder for production)
        def _encode_text(text: str) -> torch.Tensor:
            tokens = text.lower().split()
            vec = torch.zeros(self.d_model, device=DEVICE)
            for i, tok in enumerate(tokens[:64]):  # cap at 64 tokens
                h = abs(hash(tok)) % self.d_model
                vec[h] += 1
            norm = torch.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec

        keys = []
        values = []
        metadata: list[dict[str, Any]] = []

        task_vec = _encode_text(task)
        keys.append(to_numpy(task_vec).tolist())
        values.append(to_numpy(task_vec).tolist())
        metadata.append({"type": "task", "text": task[:100]})

        for doc in context_docs:
            doc_vec = _encode_text(doc)
            keys.append(to_numpy(doc_vec).tolist())
            values.append(to_numpy(doc_vec).tolist())
            metadata.append({"type": "context", "text": doc[:100]})

        return MemoryBank(keys=keys, values=values, metadata=metadata)

    def route(self, task: str, context_docs: list[str], query_vector: list[float]) -> CrossAttentionResult:
        """One-step route: encode task+context, attend against query_vector."""
        bank = self.encode(task, context_docs)
        return self.cross_attn.attend(query_vector, bank.keys, bank.values)


@dataclass
class MemoryBank:
    keys: list[list[float]]
    values: list[list[float]]
    metadata: list[dict[str, Any]]


# ── AgentAttentionLayer ────────────────────────────────────────────────────────

class AgentAttentionLayer(nn.Module):
    """
    Full attention layer for agent state fusion.

    Each agent maintains its own state vector. The attention layer
    allows agents to attend to each other's states when making
    collective decisions (consensus, task handoff, load balancing).

    Usage:
        layer = AgentAttentionLayer(num_agents=4, state_dim=128)
        fused_states = layer(agent_states)  # (num_agents, state_dim)
    """

    def __init__(self, num_agents: int = 8, state_dim: int = DEFAULT_DIMS, num_heads: int = NUM_HEADS) -> None:
        super().__init__()
        self.num_agents = num_agents
        self.state_dim = state_dim
        self.self_attn = MultiHeadAttention(state_dim, num_heads)
        self.norm = nn.LayerNorm(state_dim)
        self.ff = nn.Sequential(
            nn.Linear(state_dim, state_dim * 2),
            nn.ReLU(),
            nn.Linear(state_dim * 2, state_dim),
        )
        self.ff_norm = nn.LayerNorm(state_dim)

    def forward(self, agent_states: torch.Tensor) -> torch.Tensor:
        """
        Args:
            agent_states: (num_agents, state_dim)

        Returns:
            fused_states: (num_agents, state_dim)
        """
        # Self-attention across agents
        attn_out, _ = self.self_attn(agent_states.unsqueeze(1))
        fused = agent_states + attn_out.squeeze(1)
        fused = self.norm(fused)
        # Feed-forward
        out = fused + self.ff(self.ff_norm(fused))
        return out

    def fuse_states(self, agent_states: list[list[float]]) -> list[list[float]]:
        """Vector interface: fuse a list of agent state vectors."""
        states_t = to_tensor(agent_states)
        if states_t.dim() == 1:
            states_t = states_t.unsqueeze(0)
        out_t = self.forward(states_t)
        return [to_numpy(v).tolist() for v in out_t]


# ── Module-level helpers ──────────────────────────────────────────────────────

def scaled_dot_product(query: list[float], key: list[list[float]], value: list[list[float]]) -> tuple[list[float], list[float]]:
    attn = ScaledDotProductAttention(d_model=len(query))
    return attn.forward_single(query, key, value)


def multi_head_attention(
    query: list[float],
    context: list[list[float]],
    d_model: int = DEFAULT_DIMS,
    num_heads: int = NUM_HEADS,
) -> tuple[list[float], list[float]]:
    mha = MultiHeadAttention(d_model=d_model, num_heads=num_heads)
    return mha.forward_vector(query, context)


def cross_attend(
    query: list[float],
    keys: list[list[float]],
    values: list[list[float]],
    d_model: int = DEFAULT_DIMS,
    num_heads: int = NUM_HEADS,
) -> CrossAttentionResult:
    ca = CrossAttention(d_model=d_model, num_heads=num_heads)
    return ca.attend(query, keys, values)


def create_memory_bank(task: str, context_docs: list[str]) -> MemoryBank:
    encoder = TaskCrossEncoder()
    return encoder.encode(task, context_docs)