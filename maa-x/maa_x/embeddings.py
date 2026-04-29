"""Embeddings re-export for backward compatibility with maa_protocol."""

from maa_x.memory import (
    embed_text,
    batch_embed,
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
    'embed_text',
    'batch_embed',
    'DEFAULT_DIMS',
    'build_tfidf_vocab',
    'SemanticMemory',
    'SemanticRouter',
    'PatternMemory',
    'score_decision',
    'ReuseDecision',
    'RoutingResult',
    'SearchResult',
    'RetrievedPattern',
    'MEMORY_ROOT',
]
