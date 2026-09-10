"""Livros: ingestao, classificacao de direitos e base de conhecimento."""

from .ingest import BookIngestor, ExtractedBook, summarize_rights
from .kb import KnowledgeBase, SearchResult, chunk_text
from .rights import RightsVerdict, WorkFacts, classify, usage_policy

__all__ = [
    "BookIngestor",
    "ExtractedBook",
    "KnowledgeBase",
    "RightsVerdict",
    "SearchResult",
    "WorkFacts",
    "chunk_text",
    "classify",
    "summarize_rights",
    "usage_policy",
]
