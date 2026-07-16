from rag.config import (
    DEFAULT_TOP_K,
    MIN_SIMILARITY,
)
from rag.embeddings import OpenAIEmbeddingProvider
from rag.vector_store import ChromaVectorStore
from typing import Optional


class Retriever:
    def __init__(self):
        self.embedding_provider = (
            OpenAIEmbeddingProvider()
        )
        self.vector_store = ChromaVectorStore()

    def search(
        self,
        query: str,
        *,
        n_results: int = DEFAULT_TOP_K,
        ecosystem: Optional[str] = None,
    ) -> dict:
        if not query.strip():
            raise ValueError(
                "La consulta RAG no puede estar vacía."
            )

        query_embedding = (
            self.embedding_provider.embed_query(query)
        )

        results = self.vector_store.search(
            query_embedding=query_embedding,
            n_results=n_results,
            ecosystem=ecosystem,
        )

        top_similarity = (
            results[0]["similarity"]
            if results
            else None
        )

        evidence_sufficient = bool(
            results
            and top_similarity is not None
            and top_similarity >= MIN_SIMILARITY
        )

        return {
            "query": query,
            "ecosystem_filter": ecosystem,
            "results": results,
            "result_count": len(results),
            "top_similarity": top_similarity,
            "minimum_similarity": MIN_SIMILARITY,
            "evidence_sufficient": evidence_sufficient,
        }