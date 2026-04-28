"""
MAA Protocol — Advanced Neural Systems
======================================
Neural network components for MAA agent decision-making.
Uses PyTorch for core computations, scipy for sparse operations.

Components:
- PolicyNetwork — multi-layer perceptron for agent action scoring
- AttentionPool — weighted attention over agent state vectors
- NeuralRouter — embedding-based task routing with learned weights
- AgentStateEncoder — encode agent state into fixed-dim vector for neural processing
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# ── Config ────────────────────────────────────────────────────────────────────

WORKSPACE = Path("/root/.openclaw/workspace")
NEURAL_CACHE = WORKSPACE / "maa_protocol" / "neural_cache"
NEURAL_CACHE.mkdir(parents=True, exist_ok=True)

DEVICE = torch.device("cpu")  # use CUDA if available
DEFAULT_DIMS = 128
DROPOUT = 0.1

# ── Utilities ─────────────────────────────────────────────────────────────────

def to_tensor(x: list[float] | np.ndarray | torch.Tensor) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x
    return torch.tensor(x, dtype=torch.float32, device=DEVICE)


def to_numpy(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy()


@dataclass
class NeuralResult:
    action: str
    confidence: float
    raw_scores: dict[str, float]
    model: str
    inference_ms: float


# ── PolicyNetwork ─────────────────────────────────────────────────────────────

class PolicyNetwork(nn.Module):
    """
    MLP policy network for agent action scoring.

    Architecture: input -> linear -> relu -> dropout -> linear -> softmax
    Takes state vector, outputs action scores over N actions.

    Usage:
        model = PolicyNetwork(input_dim=128, num_actions=5, hidden_dims=[256, 128])
        action, conf, scores = model.forward(state_vector)
    """

    def __init__(
        self,
        input_dim: int = DEFAULT_DIMS,
        num_actions: int = 5,
        hidden_dims: list[int] | None = None,
        dropout: float = DROPOUT,
    ) -> None:
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [256, 128]
        self.input_dim = input_dim
        self.num_actions = num_actions

        layers = []
        prev_dim = input_dim
        for h_dim in hidden_dims:
            layers.append(nn.Linear(prev_dim, h_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(dropout))
            prev_dim = h_dim

        self.backbone = nn.Sequential(*layers)
        self.head = nn.Linear(prev_dim, num_actions)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Args:
            state: (batch, input_dim) or (input_dim,)

        Returns:
            action_scores: (num_actions,) — raw logits
        """
        if state.dim() == 1:
            state = state.unsqueeze(0)
        x = self.backbone(state)
        logits = self.head(x)
        return logits.squeeze(0) if state.shape[0] == 1 else logits

    def action_scores(self, state: torch.Tensor) -> tuple[int, float, dict[str, float]]:
        """
        Compute action from state vector.

        Returns:
            (best_action_idx, confidence, {action_name: score})
        """
        logits = self.forward(state)
        probs = F.softmax(logits, dim=-1)
        best_idx = int(torch.argmax(probs))
        confidence = float(probs[best_idx])
        scores = {f"action_{i}": float(s) for i, s in enumerate(logits.tolist())}
        return best_idx, confidence, scores


class PolicyNetworkTrainer:
    """Train PolicyNetwork via supervised gradient descent."""

    def __init__(self, model: PolicyNetwork, lr: float = 1e-3) -> None:
        self.model = model
        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)
        self.loss_fn = nn.CrossEntropyLoss()
        self._steps = 0

    def train_step(self, states: list[torch.Tensor], actions: list[int]) -> float:
        """Single training step on a batch."""
        self.model.train()
        states_t = torch.stack(states)
        actions_t = torch.tensor(actions, dtype=torch.long, device=DEVICE)
        logits = self.model.forward(states_t)
        loss = self.loss_fn(logits, actions_t)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        self._steps += 1
        return float(loss.item())

    def save(self, path: Path) -> None:
        torch.save({"model": self.model.state_dict(), "steps": self._steps}, path)

    def load(self, path: Path) -> None:
        data = torch.load(path, map_location=DEVICE)
        self.model.load_state_dict(data["model"])
        self._steps = data.get("steps", 0)


# ── AgentStateEncoder ─────────────────────────────────────────────────────────

class AgentStateEncoder:
    """
    Encode heterogeneous agent state into a fixed-dimension vector.

    Takes raw agent state (status, role, load, capabilities) and produces
    a normalised embedding suitable for PolicyNetwork input.

    Usage:
        encoder = AgentStateEncoder(output_dim=128)
        state_vector = encoder.encode({"status": "idle", "role": "researcher", "load": 0.3})
    """

    def __init__(self, output_dim: int = DEFAULT_DIMS) -> None:
        self.output_dim = output_dim
        # Learned embeddings for categorical state fields
        self.status_emb = nn.Embedding(num_embeddings=8, embedding_dim=output_dim // 4)
        self.role_emb = nn.Embedding(num_embeddings=16, embedding_dim=output_dim // 4)
        # Projection for scalar fields
        self.scalar_proj = nn.Linear(4, output_dim // 4)
        # Final projection
        self.proj = nn.Linear(output_dim // 2, output_dim)

        self._status_map = {"idle": 0, "busy": 1, "consensus": 2, "done": 3, "failed": 4, "waiting": 5, "unknown": 6}
        self._role_map: dict[str, int] = {}

    def register_role(self, role: str, idx: int | None = None) -> None:
        if idx is None:
            idx = len(self._role_map)
        self._role_map[role] = idx

    def encode(self, state: dict[str, Any]) -> torch.Tensor:
        """
        Encode raw state dict into tensor.

        Args:
            state: dict with keys like 'status', 'role', 'load', 'capabilities'
        """
        status_idx = torch.tensor(
            [self._status_map.get(state.get("status", "idle"), 6)],
            dtype=torch.long,
            device=DEVICE,
        )
        role_str = state.get("role", "unknown")
        role_idx = torch.tensor(
            [self._role_map.get(role_str, len(self._role_map))],
            dtype=torch.long,
            device=DEVICE,
        )

        status_vec = self.status_emb(status_idx).squeeze(0)
        role_vec = self.role_emb(role_idx).squeeze(0)

        # Scalar features: load (0-1), capabilities count, pending tasks, trust score
        scalars = [
            float(state.get("load", 0.0)),
            float(state.get("capabilities", 1)),
            float(state.get("pending_tasks", 0)),
            float(state.get("trust_score", 0.5)),
        ]
        scalar_vec = self.scalar_proj(to_tensor(scalars).unsqueeze(0)).squeeze(0)

        # Concatenate and project
        combined = torch.cat([status_vec, role_vec, scalar_vec])
        return self.proj(combined)


# ── AttentionPool ─────────────────────────────────────────────────────────────

class AttentionPool(nn.Module):
    """
    Weighted attention over a set of agent state vectors.

    Multi-head self-attention: allows agents to weight each other's
    state when making collective decisions (consensus, routing).

    Usage:
        pool = AttentionPool(input_dim=128, num_heads=4)
        context = pool(query_vector, candidate_vectors)
    """

    def __init__(self, input_dim: int = DEFAULT_DIMS, num_heads: int = 4) -> None:
        super().__init__()
        if input_dim % num_heads != 0:
            num_heads = 4  # fallback
        self.num_heads = num_heads
        self.head_dim = input_dim // num_heads
        self.scale = 1.0 / math.sqrt(self.head_dim)

        self.query_proj = nn.Linear(input_dim, input_dim)
        self.key_proj = nn.Linear(input_dim, input_dim)
        self.value_proj = nn.Linear(input_dim, input_dim)
        self.out_proj = nn.Linear(input_dim, input_dim)

    def forward(
        self,
        query: torch.Tensor,
        candidates: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """
        Args:
            query: (input_dim,) — single query vector
            candidates: (num_candidates, input_dim) — candidate vectors to attend over

        Returns:
            context: (input_dim,) — weighted attention output
        """
        if candidates is None:
            candidates = query.unsqueeze(0)

        if query.dim() == 1:
            query = query.unsqueeze(0)  # (1, input_dim)
        if candidates.dim() == 1:
            candidates = candidates.unsqueeze(0)

        batch_size = query.shape[0]

        Q = self.query_proj(query).view(batch_size, self.num_heads, self.head_dim).transpose(0, 1)
        K = self.key_proj(candidates).view(candidates.shape[0], self.num_heads, self.head_dim).transpose(0, 1)
        V = self.value_proj(candidates).view(candidates.shape[0], self.num_heads, self.head_dim).transpose(0, 1)

        # Attention scores: (num_heads, batch, seq_len)
        scores = torch.matmul(Q, K.transpose(-2, -1)) * self.scale
        attn = F.softmax(scores, dim=-1)

        # Weighted sum: (num_heads, batch, head_dim)
        context = torch.matmul(attn, V.transpose(0, 1))
        context = context.transpose(0, 1).contiguous().view(batch_size, -1)
        return self.out_proj(context).squeeze(0)


class AttentionPoolWrapper:
    """Stateful wrapper for AttentionPool with inference timing."""

    def __init__(self, input_dim: int = DEFAULT_DIMS, num_heads: int = 4) -> None:
        self.pool = AttentionPool(input_dim, num_heads)
        self.input_dim = input_dim
        self.num_heads = num_heads

    def attend(
        self,
        query: list[float],
        candidates: list[list[float]] | None = None,
    ) -> tuple[list[float], float]:
        """
        Run attention and return context vector + inference time.

        Returns:
            (context_vector_as_list, inference_ms)
        """
        start = time.perf_counter()
        q_t = to_tensor(query)
        c_t = to_tensor(candidates) if candidates else torch.zeros(1, self.input_dim)
        out = self.pool(q_t, c_t)
        ms = (time.perf_counter() - start) * 1000
        return to_numpy(out).tolist(), ms

    def score(self, query: list[float], target: list[float]) -> float:
        """Attention-based similarity between two vectors."""
        q_t = to_tensor(query).unsqueeze(0)
        t_t = to_tensor(target).unsqueeze(0)
        out = self.pool(q_t, t_t)
        sim = F.cosine_similarity(out, q_t).item()
        return sim


# ── NeuralRouter ──────────────────────────────────────────────────────────────

class NeuralRouter:
    """
    Learned task router using embedding similarity.

    Maintains a registry of intent embeddings and routes incoming
    tasks using learned attention weights.

    Usage:
        router = NeuralRouter(input_dim=128)
        router.register_intent("market-brief", "generate market brief for trading day")
        result = router.route("I need tomorrow's market outlook")
        # result.intent = "market-brief", result.score = 0.82
    """

    def __init__(self, input_dim: int = DEFAULT_DIMS, threshold: float = 0.5) -> None:
        self.input_dim = input_dim
        self.threshold = threshold
        self._intent_vectors: dict[str, torch.Tensor] = {}
        self._intent_descriptions: dict[str, str] = {}
        self._attention_pool = AttentionPool(input_dim=input_dim, num_heads=4)

    def register_intent(self, intent: str, description: str) -> None:
        """Register an intent with its canonical description."""
        self._intent_descriptions[intent] = description
        vec = self._encode_description(description)
        self._intent_vectors[intent] = vec

    def _encode_description(self, desc: str) -> torch.Tensor:
        """Simple hash-based encoding; replace with learned embeddings for production."""
        tokens = desc.lower().split()
        vec = torch.zeros(self.input_dim, device=DEVICE)
        for i, tok in enumerate(tokens):
            h = int(hash(tok) % self.input_dim)
            vec[h] += 1
        norm = torch.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def route(self, task_prompt: str) -> NeuralRoutingResult:
        """
        Route task to best-matching intent.

        Returns:
            NeuralRoutingResult with intent, score, decision, attention_weights
        """
        if not self._intent_vectors:
            return NeuralRoutingResult(intent="", score=0.0, decision="fresh", prompt=task_prompt)

        task_vec = self._encode_description(task_prompt)

        best_intent = ""
        best_score = 0.0
        attention_weights: dict[str, float] = {}

        for intent, intent_vec in self._intent_vectors.items():
            sim = F.cosine_similarity(task_vec, intent_vec, dim=0).item()
            attention_weights[intent] = sim
            if sim > best_score:
                best_score = sim
                best_intent = intent

        decision = "reuse" if best_score >= 0.7 else ("adapt" if best_score >= self.threshold else "fresh")
        if best_score < self.threshold:
            best_intent = ""

        return NeuralRoutingResult(
            intent=best_intent,
            score=best_score,
            decision=decision,
            prompt=task_prompt,
            attention_weights=attention_weights,
        )

    def intents(self) -> list[str]:
        return list(self._intent_vectors.keys())


@dataclass
class NeuralRoutingResult:
    intent: str
    score: float
    decision: str  # "reuse" | "adapt" | "fresh"
    prompt: str
    attention_weights: dict[str, float] = field(default_factory=dict)


# ── Module-level helpers ─────────────────────────────────────────────────────

def create_policy_network(
    input_dim: int = DEFAULT_DIMS,
    num_actions: int = 5,
    hidden_dims: list[int] | None = None,
) -> PolicyNetwork:
    return PolicyNetwork(input_dim, num_actions, hidden_dims or [256, 128])


def create_attention_pool(input_dim: int = DEFAULT_DIMS, num_heads: int = 4) -> AttentionPoolWrapper:
    return AttentionPoolWrapper(input_dim, num_heads)


def create_neural_router(input_dim: int = DEFAULT_DIMS, threshold: float = 0.5) -> NeuralRouter:
    return NeuralRouter(input_dim, threshold)


def get_device() -> str:
    return str(DEVICE)


_ACTION_NAMES = ["reuse", "adapt", "fresh", "escalate", "defer"]


def decide(query: str, confidence_hint: float = 0.5) -> NeuralResult:
    """Backward-compatible convenience API used by smoke/review tools."""
    score = max(0.0, min(1.0, float(confidence_hint)))
    if score >= 0.7:
        action = "reuse"
    elif score >= 0.5:
        action = "adapt"
    else:
        action = "fresh"
    raw_scores = {name: 0.0 for name in _ACTION_NAMES}
    raw_scores[action] = score
    return NeuralResult(
        action=action,
        confidence=score,
        raw_scores=raw_scores,
        model="heuristic-compat",
        inference_ms=0.0,
    )
