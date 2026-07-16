from pathlib import Path
from typing import Optional

import chromadb

from rag.config import (
    CHROMA_DIRECTORY,
    COLLECTION_NAME,
)
from rag.models import DocumentChunk


class ChromaVectorStore:
    def __init__(
        self,
        persist_directory: Path = CHROMA_DIRECTORY,
        collection_name: str = COLLECTION_NAME,
    ):
        persist_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.client = chromadb.PersistentClient(
            path=str(persist_directory)
        )

        self.collection_name = collection_name
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=None,
            configuration={
                "hnsw": {
                    "space": "cosine",
                }
            },
            metadata={
                "description": (
                    "Documentación técnica para el coding agent"
                ),
            },
        )

    def reset(self) -> None:
        try:
            self.client.delete_collection(
                name=self.collection_name
            )
        except Exception:
            pass

        self.collection = self._get_or_create_collection()

    def upsert(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> None:
        if len(chunks) != len(embeddings):
            raise ValueError(
                "La cantidad de chunks debe coincidir "
                "con la cantidad de embeddings."
            )

        if not chunks:
            return

        self.collection.upsert(
            ids=[
                chunk.chunk_id
                for chunk in chunks
            ],
            documents=[
                chunk.text
                for chunk in chunks
            ],
            metadatas=[
                chunk.to_metadata()
                for chunk in chunks
            ],
            embeddings=embeddings,
        )

    def search(
        self,
        query_embedding: list[float],
        *,
        n_results: int,
        ecosystem: Optional[str] = None,
    ) -> list[dict]:
        collection_count = self.collection.count()

        if collection_count == 0:
            return []

        real_n_results = min(
            n_results,
            collection_count,
        )

        query_arguments = {
            "query_embeddings": [query_embedding],
            "n_results": real_n_results,
            "include": [
                "documents",
                "metadatas",
                "distances",
            ],
        }

        if ecosystem:
            query_arguments["where"] = {
                "ecosystem": ecosystem.lower()
            }

        response = self.collection.query(
            **query_arguments
        )

        ids = response.get("ids", [[]])[0]
        documents = response.get("documents", [[]])[0]
        metadatas = response.get("metadatas", [[]])[0]
        distances = response.get("distances", [[]])[0]

        results: list[dict] = []

        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
        ):
            numeric_distance = float(distance)
            similarity = 1.0 - numeric_distance

            results.append({
                "chunk_id": chunk_id,
                "text": document,
                "metadata": metadata or {},
                "distance": round(
                    numeric_distance,
                    4,
                ),
                "similarity": round(
                    similarity,
                    4,
                ),
            })

        return results

    def count(self) -> int:
        return self.collection.count()