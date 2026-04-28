"""
MAA Protocol — Embeddings Module
===============================
Re-exports from memory.py for backward compatibility.
The real embedding system lives in maa_protocol.memory.
"""

from maa_protocol.memory import (
    embed_text,
    batch_embed,
    EmbeddingVector,
    DEFAULT_DIMS,
    build_tfidf_vocab,
    SemanticMemory,
    SemanticRouter,
    PatternMemory,
    score_decision,
    ReuseDecision,
    RoutingResult,
    SearchResult,
    RetrievedPattern,
    MEMORY_ROOT,
)

__all__ = [
    "embed_text",
    "batch_embed",
    "EmbeddingVector",
    "DEFAULT_DIMS",
    "build_tfidf_vocab",
    "SemanticMemory",
    "SemanticRouter",
    "PatternMemory",
    "score_decision",
    "ReuseDecision",
    "RoutingResult",
    "SearchResult",
    "RetrievedPattern",
    "MEMORY_ROOT",
]