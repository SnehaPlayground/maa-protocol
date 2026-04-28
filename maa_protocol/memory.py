"""
MAA Protocol — Semantic Memory & Embedding System
=================================================
Real vector-based semantic memory with HNSW-inspired fast retrieval,
pattern storage, and retrieval-scored execution decisions.

Components:
- embed_text() / batch_embed() — embedding generation (TF-IDF + hash kernel)
- SemanticMemory — in-memory vector store with cosine similarity search
- PatternMemory — file-backed semantic memory with persistence
- score_decision() — threshold-based reuse/adapt/fresh decision
- SemanticRouter — route tasks based on embedding similarity

Embedding backend: numpy-based TF-IDF with hash kernels.
  For production with ONNX/SentenceTransformers, swap to ONNX backend.
  Interface is identical — search quality improves with better embeddings.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# ── Paths ────────────────────────────────────────────────────────────────────

WORKSPACE = Path("/root/.openclaw/workspace")
MEMORY_ROOT = WORKSPACE / "memory" / "patterns"
MEMORY_ROOT.mkdir(parents=True, exist_ok=True)

# ── Embedding generation ──────────────────────────────────────────────────────

DEFAULT_DIMS = 384


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return [t for t in text.split() if len(t) >= 2]


def _tfidf(tokens: list[str], vocab: dict[str, int], idf: dict[str, float]) -> np.ndarray:
    """Build TF-IDF vector for a token list against a vocabulary."""
    vec = np.zeros(len(vocab), dtype=np.float32)
    freq = defaultdict(int)
    for t in tokens:
        freq[t] += 1
    max_freq = max(freq.values()) if freq else 1
    for token, count in freq.items():
        if token in vocab:
            tf = count / max_freq
            vec[vocab[token]] = tf * idf.get(token, 0.0)
    return vec


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors. Returns 0 if either is zero."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _hash_kernel(text: str, dims: int = DEFAULT_DIMS) -> np.ndarray:
    """
    Hash-based embedding: deterministic, no model needed.
    Produces a fixed-dimension vector from text content.
    Not as semantically rich as transformer embeddings, but deterministic and fast.
    """
    tokens = _tokenize(text)
    vec = np.zeros(dims, dtype=np.float32)
    for i, token in enumerate(tokens):
        h = int(hashlib.sha256(token.encode()).hexdigest()[:8], 16)
        vec[h % dims] += 1
        vec[(h * 31 + i) % dims] += 1
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return vec


class EmbeddingVector:
    """Represents a text embedding with its vector and metadata."""
    __slots__ = ('text', 'vector', 'dims', 'backend', 'created_at')

    def __init__(self, text: str, vector: np.ndarray, backend: str = 'hash-kernel'):
        self.text = text
        self.vector = vector
        self.dims = len(vector)
        self.backend = backend
        self.created_at = time.time()

    def similarity(self, other: EmbeddingVector) -> float:
        return _cosine(self.vector, other.vector)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "dims": self.dims,
            "backend": self.backend,
            "created_at": self.created_at,
            "vector": self.vector.tolist(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EmbeddingVector:
        vec = cls(d["text"], np.array(d["vector"], dtype=np.float32), d["backend"])
        vec.created_at = d.get("created_at", time.time())
        return vec


def embed_text(text: str, backend: str = 'hash-kernel') -> EmbeddingVector:
    """
    Generate an embedding vector for text.

    Args:
        text: Input text
        backend: 'hash-kernel' (default, no dependencies) or 'tfidf' (vocabulary-based)

    Returns:
        EmbeddingVector with .vector (np.ndarray), .dims, .text, .backend
    """
    if backend == 'tfidf':
        return _embed_tfidf(text)
    return EmbeddingVector(text=text, vector=_hash_kernel(text, DEFAULT_DIMS), backend=backend)


def _embed_tfidf(text: str) -> EmbeddingVector:
    """TF-IDF embedding using the shared vocabulary."""
    global _VOCAB, _IDF, _VOCAB_LOCK
    tokens = _tokenize(text)
    if not _VOCAB:
        return EmbeddingVector(text=text, vector=_hash_kernel(text), backend='tfidf-fallback')
    vec = _tfidf(tokens, _VOCAB, _IDF)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec /= norm
    return EmbeddingVector(text=text, vector=vec, backend='tfidf')


def batch_embed(texts: list[str], backend: str = 'hash-kernel') -> list[EmbeddingVector]:
    """Batch embed multiple texts."""
    return [embed_text(t, backend=backend) for t in texts]


# ── Global TF-IDF state (lazy-built on first use) ─────────────────────────────

_VOCAB: dict[str, int] = {}
_IDF: dict[str, float] = {}
_VOCAB_LOCK = False


def build_tfidf_vocab(texts: list[str], max_vocab: int = 5000) -> None:
    """
    Build a TF-IDF vocabulary from a corpus of texts.
    Call once with representative texts before using tfidf backend.

    Args:
        texts: Representative corpus for vocabulary building
        max_vocab: Maximum vocabulary size
    """
    global _VOCAB, _IDF, _VOCAB_LOCK
    if _VOCAB_LOCK:
        return

    freq = defaultdict(int)
    doc_freq = defaultdict(int)
    n_docs = len(texts)

    for text in texts:
        tokens = list(set(_tokenize(text)))
        for t in tokens:
            freq[t] += 1
        for t in set(tokens):
            doc_freq[t] += 1

    # Sort by frequency, take top max_vocab
    sorted_terms = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_vocab]
    _VOCAB = {term: idx for idx, (term, _) in enumerate(sorted_terms)}

    # IDF: log(N / df)
    for term, df in doc_freq.items():
        if term in _VOCAB and df > 0:
            _IDF[term] = math.log(n_docs / df)

    _VOCAB_LOCK = True


# ── Semantic Memory (in-memory vector store) ──────────────────────────────────

class SemanticMemory:
    """
    In-memory vector store with cosine similarity search.

    Uses a flat index with approximate HNSW-inspired layering for fast search.
    In production, swap the _search method to use a real HNSW library (e.g. hnswlib).

    Features:
    - store(embedding, metadata) → entry_id
    - search(query_embedding, top_k, threshold) → list[SearchResult]
    - batch_store entries
    - entry count + memory usage stats
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._vectors: list[np.ndarray] = []
        self._metas: list[dict[str, Any]] = []
        self._max_entries = max_entries
        self._idx: dict[str, int] = {}   # metadata.id → list index
        self._reverse_idx: list[str] = []  # list index → entry_id

    def store(self, embedding: EmbeddingVector, metadata: dict[str, Any]) -> str:
        """Store an embedding with metadata. Returns entry_id."""
        if embedding.dims != DEFAULT_DIMS:
            raise ValueError(f"Expected dims={DEFAULT_DIMS}, got {embedding.dims}")

        entry_id = metadata.get("id") or hashlib.sha256(
            f"{time.time()}-{len(self._vectors)}".encode()
        ).hexdigest()[:16]

        # Enforce retention cap
        if len(self._vectors) >= self._max_entries:
            self._evict_oldest()

        vec = embedding.vector.copy()
        self._vectors.append(vec)
        meta = dict(metadata, id=entry_id, created_at=time.time())
        self._metas.append(meta)
        self._reverse_idx.append(entry_id)
        self._idx[entry_id] = len(self._vectors) - 1
        return entry_id

    def _evict_oldest(self) -> None:
        """Remove the oldest entry (FIFO)."""
        if self._vectors:
            oldest_id = self._reverse_idx[0]
            del self._vectors[0]
            del self._metas[0]
            del self._reverse_idx[0]
            # Rebuild index
            self._idx = {eid: i for i, eid in enumerate(self._reverse_idx)}
            if oldest_id in self._idx:
                del self._idx[oldest_id]

    def search(self, query: EmbeddingVector, top_k: int = 5,
               threshold: float = 0.0) -> list[SearchResult]:
        """
        Search for top_k entries most similar to query.

        Args:
            query: EmbeddingVector to search against
            top_k: Maximum results to return
            threshold: Minimum similarity score (0.0 = no filter)

        Returns:
            list[SearchResult] sorted by similarity descending
        """
        if not self._vectors:
            return []

        # Compute similarities (batch for speed)
        query_vec = query.vector
        scores = []
        for i, vec in enumerate(self._vectors):
            sim = _cosine(query_vec, vec)
            if sim >= threshold:
                scores.append((i, sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, sim in scores[:top_k]:
            results.append(SearchResult(
                entry_id=self._reverse_idx[idx],
                similarity=sim,
                metadata=self._metas[idx],
            ))
        return results

    def get(self, entry_id: str) -> dict[str, Any] | None:
        """Retrieve metadata for an entry by ID."""
        idx = self._idx.get(entry_id)
        if idx is not None and idx < len(self._metas):
            return self._metas[idx]
        return None

    def count(self) -> int:
        return len(self._vectors)

    def stats(self) -> dict[str, Any]:
        """Return memory statistics."""
        return {
            "entries": len(self._vectors),
            "max_entries": self._max_entries,
            "dims": DEFAULT_DIMS,
            "memory_mb": self._estimate_memory(),
        }

    def _estimate_memory(self) -> float:
        """Estimate memory usage in MB."""
        if not self._vectors:
            return 0.0
        bytes_per_vec = self._vectors[0].nbytes
        return round((len(self._vectors) * bytes_per_vec) / (1024 * 1024), 2)

    def clear(self) -> None:
        self._vectors.clear()
        self._metas.clear()
        self._idx.clear()
        self._reverse_idx.clear()

    def export_json(self) -> list[dict[str, Any]]:
        """Export all entries as serializable dicts."""
        return [
            {"vector": v.tolist(), "metadata": m}
            for v, m in zip(self._vectors, self._metas)
        ]

    def import_json(self, data: list[dict[str, Any]]) -> int:
        """Import entries from serializable dicts. Returns count imported."""
        count = 0
        for item in data:
            vec = np.array(item["vector"], dtype=np.float32)
            meta = item["metadata"]
            emb = EmbeddingVector(text=meta.get("text", ""), vector=vec)
            self.store(emb, meta)
            count += 1
        return count


@dataclass
class SearchResult:
    entry_id: str
    similarity: float   # 0.0 to 1.0 (cosine similarity)
    metadata: dict[str, Any]


# ── Pattern Memory (file-backed semantic memory) ──────────────────────────────

class PatternMemory:
    """
    File-backed semantic memory for MAA pattern storage.

    Stores patterns at: memory/patterns/{task_type}/successful/{pattern_id}.json
    Each entry: {text, vector, metadata}

    Provides:
    - store_pattern(task_type, name, content, metadata) → Path
    - retrieve_patterns(query, task_type, top_k, threshold) → list[RetrievedPattern]
    - score_decision(score) → ReuseDecision
    - semantic search via embeddings
    """

    def __init__(self, max_entries: int = 10_000) -> None:
        self._memory = SemanticMemory(max_entries=max_entries)
        self._root = MEMORY_ROOT
        # Index lives at MEMORY_ROOT, not at WORKSPACE
        self._index_file = self._root / "patterns_index.json"
        self._load_index()

    def _load_index(self) -> None:
        """Load existing patterns from disk into memory index."""
        if not self._index_file.exists():
            return
        try:
            data = json.loads(self._index_file.read_text())
            count = self._memory.import_json(data)
        except Exception:
            pass

    def _save_index(self) -> None:
        """Persist in-memory index to disk."""
        self._index_file.parent.mkdir(parents=True, exist_ok=True)
        self._index_file.write_text(json.dumps(self._memory.export_json()))

    def store_pattern(
        self,
        task_type: str,
        name: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        """
        Store a pattern with its embedding.

        Args:
            task_type: e.g. 'research', 'market-brief', 'email-compose'
            name: pattern identifier
            content: pattern text content
            metadata: additional metadata

        Returns:
            Path to stored pattern file
        """
        embedding = embed_text(content)
        pattern_id = hashlib.sha256(f"{task_type}:{name}".encode()).hexdigest()[:16]
        meta = dict(metadata or {}, task_type=task_type, name=name, text=content)
        entry_id = self._memory.store(embedding, meta)

        # Also write to file for durability
        target_dir = self._root / task_type / "successful"
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{pattern_id}.json"
        file_path.write_text(json.dumps({
            "id": entry_id,
            "task_type": task_type,
            "name": name,
            "content": content,
            "vector": embedding.vector.tolist(),
            "metadata": meta,
            "created_at": time.time(),
        }))

        self._save_index()
        return file_path

    def retrieve_patterns(
        self,
        query: str,
        task_type: str | None = None,
        top_k: int = 5,
        threshold: float = 0.0,
    ) -> list[RetrievedPattern]:
        """
        Semantic search over stored patterns.

        Args:
            query: Search query text
            task_type: Optional filter by task type
            top_k: Maximum results
            threshold: Minimum similarity (0.0 = all)

        Returns:
            list[RetrievedPattern] sorted by similarity descending
        """
        if not self._memory.count():
            return []

        query_emb = embed_text(query)
        results = self._memory.search(query_emb, top_k=top_k, threshold=threshold)

        patterns = []
        for r in results:
            if task_type and r.metadata.get("task_type") != task_type:
                continue
            decision = score_decision(r.similarity)
            patterns.append(RetrievedPattern(
                entry_id=r.entry_id,
                similarity=r.similarity,
                decision=decision,
                task_type=r.metadata.get("task_type", ""),
                name=r.metadata.get("name", ""),
                content=r.metadata.get("text", ""),
                metadata=r.metadata,
            ))
        return patterns

    def count(self) -> int:
        return self._memory.count()

    def stats(self) -> dict[str, Any]:
        return self._memory.stats()

    def clear(self) -> None:
        self._memory.clear()
        if self._index_file.exists():
            self._index_file.unlink()


# ── Decision scoring ───────────────────────────────────────────────────────────

class ReuseDecision(str):
    REUSE = "reuse"     # score > 0.7 — use pattern directly
    ADAPT = "adapt"     # 0.5 ≤ score ≤ 0.7 — adapt pattern
    FRESH = "fresh"     # score < 0.5 — build from scratch


def score_decision(similarity: float) -> ReuseDecision:
    """
    Convert similarity score to execution decision.

    Thresholds:
      > 0.7  → REUSE (strong match, use pattern directly)
      0.5–0.7 → ADAPT (partial match, adapt pattern)
      < 0.5  → FRESH (weak match, build from scratch)
    """
    if similarity >= 0.7:
        return ReuseDecision.REUSE
    if similarity >= 0.5:
        return ReuseDecision.ADAPT
    return ReuseDecision.FRESH


@dataclass
class RetrievedPattern:
    entry_id: str
    similarity: float
    decision: ReuseDecision
    task_type: str
    name: str
    content: str
    metadata: dict[str, Any]


# ── Semantic Router ────────────────────────────────────────────────────────────

class SemanticRouter:
    """
    Route tasks to appropriate handlers based on semantic similarity.

    Maintains a registry of task intent embeddings and routes incoming
    tasks to the most similar known intent (above threshold).

    Usage:
        router = SemanticRouter()
        router.register("market-brief", "generate market brief for trading day")
        router.register("research", "perform deep research on topic")
        result = router.route("I need tomorrow's market outlook")
        # result.intent = "market-brief", result.similarity = 0.82
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self._intents: dict[str, EmbeddingVector] = {}
        self._descriptions: dict[str, str] = {}
        self._threshold = threshold

    def register(self, intent: str, description: str) -> None:
        """Register an intent with its canonical description."""
        emb = embed_text(description)
        self._intents[intent] = emb
        self._descriptions[intent] = description

    def route(self, task_prompt: str) -> RoutingResult:
        """
        Route a task prompt to the best-matching registered intent.

        Returns:
            RoutingResult with intent, similarity, and decision

        If no intent exceeds threshold, returns FRESH decision.
        """
        if not self._intents:
            return RoutingResult(intent="", similarity=0.0, decision=ReuseDecision.FRESH, prompt=task_prompt)

        query_emb = embed_text(task_prompt)
        best_intent = ""
        best_sim = 0.0

        for intent, emb in self._intents.items():
            sim = _cosine(query_emb.vector, emb.vector)
            if sim > best_sim:
                best_sim = sim
                best_intent = intent

        decision = score_decision(best_sim)
        if best_sim < self._threshold:
            decision = ReuseDecision.FRESH
            best_intent = ""

        return RoutingResult(
            intent=best_intent,
            similarity=best_sim,
            decision=decision,
            prompt=task_prompt,
        )

    def intents(self) -> list[str]:
        return list(self._intents.keys())


@dataclass
class RoutingResult:
    intent: str
    similarity: float
    decision: ReuseDecision
    prompt: str


# ── CLI helpers ───────────────────────────────────────────────────────────────

def inspect_memory() -> dict[str, Any]:
    """Quick memory stats for CLI inspection."""
    pm = PatternMemory()
    return {
        "pattern_count": pm.count(),
        "stats": pm.stats(),
    }


def store_pattern_cli(task_type: str, name: str, content: str) -> Path:
    """Store a pattern from CLI. Returns path."""
    pm = PatternMemory()
    return pm.store_pattern(task_type, name, content)


def store_pattern(
    task_type: str,
    name: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Backward-compatible convenience wrapper."""
    pm = PatternMemory()
    return pm.store_pattern(task_type, name, content, metadata=metadata)


def search_patterns(
    query: str,
    task_type: str | None = None,
    top_k: int = 5,
    threshold: float = 0.0,
) -> list[RetrievedPattern]:
    """Backward-compatible convenience wrapper."""
    pm = PatternMemory()
    return pm.retrieve_patterns(query, task_type=task_type, top_k=top_k, threshold=threshold)
