from llm_client import get_client
from rag.config import EMBEDDING_MODEL


class OpenAIEmbeddingProvider:
    def __init__(
        self,
        model: str = EMBEDDING_MODEL,
    ):
        self.model = model
        self.client = get_client()

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
        )

        ordered_data = sorted(
            response.data,
            key=lambda item: item.index,
        )

        return [
            item.embedding
            for item in ordered_data
        ]

    def embed_query(
        self,
        query: str,
    ) -> list[float]:
        embeddings = self.embed_texts([query])

        if not embeddings:
            raise RuntimeError(
                "No se pudo generar el embedding de la consulta."
            )

        return embeddings[0]