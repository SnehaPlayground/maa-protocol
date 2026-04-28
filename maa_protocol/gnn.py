"""
MAA Protocol — GNN Layers (Graph Neural Networks)
===================================================
Graph neural network layers for agent topology and swarm relationship modeling.

Uses networkx for graph structure + PyTorch for message passing.

Components:
- AgentGraph — networkx graph representing agent relationships
- GNNMessagePasser — simple message passing layer (GCN-inspired)
- TopologyGNN — full GNN model for learning agent relationship embeddings
- AgentTopologyEncoder — encode agent graph state into GNN input format
- SwarnGNN — GNN wrapper for swarm-level predictions

Usage:
    gnn = TopologyGNN(num_nodes=8, node_dim=128, hidden_dim=128)
    embeddings = gnn.forward(adjacency_matrix, node_features)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import networkx as nx
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

DEVICE = torch.device("cpu")
DEFAULT_DIMS = 128


def to_tensor(x: list[float] | np.ndarray | torch.Tensor) -> torch.Tensor:
    if isinstance(x, torch.Tensor):
        return x
    return torch.tensor(x, dtype=torch.float32, device=DEVICE)


def to_numpy(t: torch.Tensor) -> np.ndarray:
    return t.detach().cpu().numpy()


# ── AgentGraph ────────────────────────────────────────────────────────────────

class AgentGraph:
    """
    NetworkX graph representing agent topology.

    Nodes = agents, edges = relationships (can_delegate, trusts, routes_to, etc.).

    Usage:
        graph = AgentGraph()
        graph.add_agent("a1", role="coordinator", load=0.3)
        graph.add_agent("a2", role="coder")
        graph.add_edge("a1", "a2", relationship="routes_to", weight=1.0)
        adj = graph.adjacency_matrix()
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self._agent_features: dict[str, dict[str, Any]] = {}

    def add_agent(self, agent_id: str, **features: Any) -> None:
        self.graph.add_node(agent_id, **features)
        self._agent_features[agent_id] = features

    def add_edge(self, from_id: str, to_id: str, **features: Any) -> None:
        self.graph.add_edge(from_id, to_id, **features)

    def remove_agent(self, agent_id: str) -> None:
        if agent_id in self._agent_features:
            del self._agent_features[agent_id]
        self.graph.remove_node(agent_id)

    def adjacency_matrix(self) -> np.ndarray:
        return nx.to_numpy_array(self.graph, dtype=np.float32)

    def degree(self) -> dict[str, int]:
        return dict(self.graph.degree())

    def neighbors(self, agent_id: str) -> list[str]:
        return list(self.graph.neighbors(agent_id))

    def agent_features(self, agent_id: str) -> dict[str, Any]:
        return self._agent_features.get(agent_id, {})

    def node_feature_vector(self, agent_id: str, dim: int = DEFAULT_DIMS) -> np.ndarray:
        """Encode agent features into a fixed-dim vector."""
        feat = self._agent_features.get(agent_id, {})
        vec = np.zeros(dim, dtype=np.float32)

        # Encode categorical
        role = feat.get("role", "unknown")
        role_h = abs(hash(role)) % dim
        vec[role_h] = 1.0

        # Encode scalar: load (0-1), trust (0-1), capabilities
        vec[(role_h + 37) % dim] = feat.get("load", 0.0)
        vec[(role_h + 73) % dim] = feat.get("trust", 0.5)
        vec[(role_h + 101) % dim] = feat.get("capabilities", 1.0) / 10.0

        return vec

    def to_node_feature_matrix(self, dim: int = DEFAULT_DIMS) -> torch.Tensor:
        """Return (num_nodes, dim) tensor of all node features."""
        agents = list(self.graph.nodes())
        features = [self.node_feature_vector(a, dim) for a in agents]
        return to_tensor(features)

    def num_agents(self) -> int:
        return self.graph.number_of_nodes()


# ── GNNMessagePasser ─────────────────────────────────────────────────────────

class GNNMessagePasser(nn.Module):
    """
    Simple GCN-inspired message passing layer.

    Aggregate neighbor features via mean pooling, then update via linear proj.

    forward(adjacency, node_features) -> updated_node_features
    """

    def __init__(self, node_dim: int = DEFAULT_DIMS, hidden_dim: int = 128) -> None:
        super().__init__()
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim
        self.W = nn.Linear(node_dim, hidden_dim)
        self.norm = nn.LayerNorm(hidden_dim)
        self.reset_parameters()

    def reset_parameters(self) -> None:
        nn.init.xavier_uniform_(self.W.weight)
        nn.init.zeros_(self.W.bias)

    def forward(self, adj: torch.Tensor, node_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            adj: (num_nodes, num_nodes) — adjacency matrix (0/1 or weighted)
            node_features: (num_nodes, node_dim)

        Returns:
            updated_features: (num_nodes, hidden_dim)
        """
        num_nodes = adj.shape[0]
        I = torch.eye(num_nodes, device=DEVICE)
        A_hat = adj + I
        deg = A_hat.sum(dim=1, keepdim=True)
        deg = torch.where(deg > 0, deg, torch.ones_like(deg))
        D_norm = 1.0 / deg
        A_norm = A_hat * D_norm
        aggregated = torch.matmul(A_norm, node_features)
        projected = self.W(aggregated)
        projected = self.norm(projected)
        return F.relu(projected)


class GNNMessagePasserWrapper:
    """Vector-friendly wrapper around GNNMessagePasser."""

    def __init__(self, node_dim: int = DEFAULT_DIMS, hidden_dim: int = 128) -> None:
        self.passer = GNNMessagePasser(node_dim, hidden_dim)
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim

    def pass_messages(
        self,
        adjacency: list[list[float]],
        node_features: list[list[float]],
    ) -> tuple[list[list[float]], float]:
        """
        Run one message passing step.

        Returns:
            (updated_node_features, inference_ms)
        """
        start = time.perf_counter()
        adj_t = to_tensor(adjacency)
        feat_t = to_tensor(node_features)
        out_t = self.passer(adj_t, feat_t)
        ms = (time.perf_counter() - start) * 1000
        return [to_numpy(v).tolist() for v in out_t], ms

    def aggregate_neighbors(
        self,
        adjacency: list[list[float]],
        node_features: list[list[float]],
    ) -> list[list[float]]:
        """Aggregate neighbor features (no update)."""
        adj_t = to_tensor(adjacency)
        feat_t = to_tensor(node_features)
        num_nodes = adj_t.shape[0]

        I = torch.eye(num_nodes, device=DEVICE)
        A_hat = adj_t + I
        deg = A_hat.sum(dim=1, keepdim=True)
        deg = torch.where(deg > 0, deg, torch.ones_like(deg))
        D_norm = 1.0 / deg
        A_norm = A_hat * D_norm
        aggregated = torch.matmul(A_norm, feat_t)
        return [to_numpy(v).tolist() for v in aggregated]


# ── TopologyGNN ───────────────────────────────────────────────────────────────

class TopologyGNN(nn.Module):
    """
    Multi-layer GNN for agent topology learning.

    Stacks GNNMessagePasser layers with ReLU + residual connections.

    Usage:
        gnn = TopologyGNN(num_nodes=8, node_dim=128, hidden_dim=128, num_layers=3)
        embeddings = gnn.forward(adjacency_matrix, node_features)
        # embeddings shape: (num_nodes, hidden_dim)
    """

    def __init__(
        self,
        num_nodes: int = 8,
        node_dim: int = DEFAULT_DIMS,
        hidden_dim: int = 128,
        num_layers: int = 3,
    ) -> None:
        super().__init__()
        self.num_nodes = num_nodes
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim

        # Input projection
        self.input_proj = nn.Linear(node_dim, hidden_dim)

        # Stacked message passing layers
        self.layers = nn.ModuleList([
            GNNMessagePasser(hidden_dim, hidden_dim)
            for _ in range(num_layers)
        ])

        # Output head
        self.output_head = nn.Linear(hidden_dim, hidden_dim)

    def forward(self, adj: torch.Tensor, node_features: torch.Tensor) -> torch.Tensor:
        """
        Args:
            adj: (num_nodes, num_nodes)
            node_features: (num_nodes, node_dim)

        Returns:
            embeddings: (num_nodes, hidden_dim)
        """
        x = self.input_proj(node_features)
        x = F.relu(x)

        for layer in self.layers:
            x_new = layer(adj, x)
            x = F.relu(x_new)

        return self.output_head(x)

    def embed(self, graph: AgentGraph) -> torch.Tensor:
        """
        Convenience: run GNN on an AgentGraph and return embeddings.

        Returns:
            (num_agents, hidden_dim) embedding tensor
        """
        adj_t = to_tensor(graph.adjacency_matrix())
        feat_t = graph.to_node_feature_matrix(self.node_dim)
        return self.forward(adj_t, feat_t)

    def predict_edge(
        self,
        from_embedding: torch.Tensor,
        to_embedding: torch.Tensor,
    ) -> float:
        """
        Predict edge likelihood between two agent embeddings.

        Returns:
            probability that from_agent routes to to_agent
        """
        # Dot product of two embeddings, scaled to (0,1)
        score = torch.dot(from_embedding, to_embedding)
        prob = torch.sigmoid(score / (self.hidden_dim ** 0.5)).item()
        return prob


class TopologyGNNWrapper:
    """Vector-friendly TopologyGNN wrapper."""

    def __init__(self, num_nodes: int = 8, node_dim: int = DEFAULT_DIMS, hidden_dim: int = 128, num_layers: int = 3) -> None:
        self.model = TopologyGNN(num_nodes, node_dim, hidden_dim, num_layers)
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim

    def run(self, adjacency: list[list[float]], node_features: list[list[float]]) -> list[list[float]]:
        start = time.perf_counter()
        adj_t = to_tensor(adjacency)
        feat_t = to_tensor(node_features)
        out_t = self.model(adj_t, feat_t)
        return [to_numpy(v).tolist() for v in out_t]

    def embed_graph(self, graph: AgentGraph) -> list[list[float]]:
        embeddings = self.model.embed(graph)
        return [to_numpy(v).tolist() for v in embeddings]


# ── AgentTopologyEncoder ──────────────────────────────────────────────────────

class AgentTopologyEncoder:
    """
    Encode agent + graph structure into GNN inputs.

    Builds node feature matrix and adjacency matrix from agent state.

    Usage:
        encoder = AgentTopologyEncoder(node_dim=128)
        adj, features = encoder.encode(graph)
        embeddings = gnn.forward(adj, features)
    """

    def __init__(self, node_dim: int = DEFAULT_DIMS) -> None:
        self.node_dim = node_dim

    def encode(self, graph: AgentGraph) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Encode AgentGraph into (adjacency, node_features).

        Returns:
            (adjacency_matrix, node_feature_matrix)
        """
        adj_t = to_tensor(graph.adjacency_matrix())
        feat_t = graph.to_node_feature_matrix(self.node_dim)
        return adj_t, feat_t

    def encode_vector(self, graph: AgentGraph) -> tuple[list[list[float]], list[list[float]]]:
        """Vector interface."""
        adj_t, feat_t = self.encode(graph)
        return to_numpy(adj_t).tolist(), to_numpy(feat_t).tolist()


# ── SwarmGNN ─────────────────────────────────────────────────────────────────

class SwarmGNN:
    """
    Swarm-level GNN for predicting agent behavior and topology optimization.

    Uses TopologyGNN to learn embeddings, then applies pooling for swarm-level predictions.

    Usage:
        sgnn = SwarmGNN(num_agents=8)
        embeddings = sgnn.embed(graph)
        prediction = sgnn.predict_delegation(graph, from_agent, to_agent)
    """

    def __init__(
        self,
        num_agents: int = 8,
        node_dim: int = DEFAULT_DIMS,
        hidden_dim: int = 128,
        num_layers: int = 3,
    ) -> None:
        self.num_agents = num_agents
        self.node_dim = node_dim
        self.gnn = TopologyGNN(num_agents, node_dim, hidden_dim, num_layers)
        self.encoder = AgentTopologyEncoder(node_dim)

    def embed(self, graph: AgentGraph) -> torch.Tensor:
        return self.gnn.embed(graph)

    def pool(self, embeddings: torch.Tensor, mode: str = "mean") -> torch.Tensor:
        """Pool node embeddings into a single swarm-level vector."""
        if mode == "mean":
            return embeddings.mean(dim=0)
        if mode == "max":
            return embeddings.max(dim=0)[0]
        if mode == "sum":
            return embeddings.sum(dim=0)
        return embeddings.mean(dim=0)

    def predict_delegation(
        self,
        graph: AgentGraph,
        from_id: str,
        to_id: str,
    ) -> DelegationPrediction:
        """
        Predict likelihood that from_id delegates to to_id.

        Returns:
            DelegationPrediction with probability, reason
        """
        agents = list(graph.graph.nodes())
        from_idx = agents.index(from_id) if from_id in agents else -1
        to_idx = agents.index(to_id) if to_id in agents else -1

        embeddings = self.embed(graph)

        if from_idx < 0 or to_idx < 0:
            return DelegationPrediction(probability=0.0, reason="agent not in graph")

        from_emb = embeddings[from_idx]
        to_emb = embeddings[to_idx]
        prob = self.gnn.predict_edge(from_emb, to_emb)

        # Simple reason: check graph edges and degree
        neighbors = graph.neighbors(from_id)
        reason = f"direct edge in graph" if to_id in neighbors else "inferred via topology"
        if graph.degree()[from_id] == 0:
            reason = "isolated agent, using topology inference"

        return DelegationPrediction(probability=prob, reason=reason)


@dataclass
class DelegationPrediction:
    probability: float
    reason: str


# ── Module-level helpers ──────────────────────────────────────────────────────

def create_topology_gnn(
    num_nodes: int = 8,
    node_dim: int = DEFAULT_DIMS,
    hidden_dim: int = 128,
    num_layers: int = 3,
) -> TopologyGNNWrapper:
    return TopologyGNNWrapper(num_nodes, node_dim, hidden_dim, num_layers)


def create_swarm_gnn(
    num_agents: int = 8,
    node_dim: int = DEFAULT_DIMS,
    hidden_dim: int = 128,
) -> SwarmGNN:
    return SwarmGNN(num_agents, node_dim, hidden_dim)


def encode_graph(graph: AgentGraph) -> tuple[list[list[float]], list[list[float]]]:
    enc = AgentTopologyEncoder()
    return enc.encode_vector(graph)