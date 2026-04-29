"""GNN layers for agent topology modeling (pure Python / networkx fallback)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class AgentGraph:
    num_nodes: int = 8
    adjacency: list[list[float]] | None = None

    def __post_init__(self) -> None:
        if self.adjacency is None:
            self.adjacency = [[0.0] * self.num_nodes for _ in range(self.num_nodes)]

    def add_edge(self, i: int, j: int, weight: float = 1.0) -> None:
        if self.adjacency and 0 <= i < self.num_nodes and 0 <= j < self.num_nodes:
            self.adjacency[i][j] = weight

    def degree(self, node: int) -> float:
        if self.adjacency is None:
            return 0.0
        return sum(self.adjacency[node])


class GNNMessagePasser:
    def __init__(self, node_dim: int = 128, hidden_dim: int = 128) -> None:
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim

    def message_pass(self, node_features: list[list[float]], adjacency: list[list[float]]) -> list[list[float]]:
        features = np.array(node_features, dtype=np.float32)
        adj = np.array(adjacency, dtype=np.float32)
        d = adj.sum(axis=1, keepdims=True)
        d[d == 0] = 1.0
        agg = adj @ features
        normalized = agg / d
        out = np.tanh(normalized @ np.eye(self.node_dim))
        return out.tolist()


class TopologyGNN:
    def __init__(self, num_nodes: int = 8, node_dim: int = 128, hidden_dim: int = 128) -> None:
        self.num_nodes = num_nodes
        self.node_dim = node_dim
        self.hidden_dim = hidden_dim
        self.mpasser = GNNMessagePasser(node_dim, hidden_dim)

    def forward(self, adjacency: list[list[float]], node_features: list[list[float]]) -> list[list[float]]:
        return self.mpasser.message_pass(node_features, adjacency)

    def predict_link(self, node_i: int, node_j: int, embeddings: list[list[float]]) -> float:
        if not embeddings or node_i >= len(embeddings) or node_j >= len(embeddings):
            return 0.0
        ei = np.array(embeddings[node_i], dtype=np.float32)
        ej = np.array(embeddings[node_j], dtype=np.float32)
        return float(np.dot(ei, ej) / (np.linalg.norm(ei) * np.linalg.norm(ej) + 1e-9))


@dataclass
class SwarnGNN:
    num_nodes: int = 8
    node_dim: int = 128

    def predict_swarm_state(self, adjacency: list[list[float]], node_features: list[list[float]]) -> dict[str, Any]:
        gnn = TopologyGNN(self.num_nodes, self.node_dim)
        embeddings = gnn.forward(adjacency, node_features)
        avg_embedding = np.mean(embeddings, axis=0).tolist()
        return {'embeddings': embeddings, 'avg_embedding': avg_embedding, 'stability': 1.0}


def create_agent_graph(num_agents: int = 8) -> AgentGraph:
    return AgentGraph(num_nodes=num_agents)


def create_topology_gnn(num_nodes: int = 8, node_dim: int = 128) -> TopologyGNN:
    return TopologyGNN(num_nodes=num_nodes, node_dim=node_dim)
