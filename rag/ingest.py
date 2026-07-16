import argparse
import json

from rag.chunker import MarkdownChunker
from rag.config import RAW_DOCUMENTS_DIR
from rag.document_loader import DocumentLoader
from rag.embeddings import OpenAIEmbeddingProvider
from rag.vector_store import ChromaVectorStore


DEFAULT_BATCH_SIZE = 50


def ingest(
    *,
    reset: bool,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict:
    loader = DocumentLoader(
        raw_documents_dir=RAW_DOCUMENTS_DIR
    )

    documents = loader.load_all()

    if not documents:
        raise RuntimeError(
            "No se encontraron documentos en "
            f"{RAW_DOCUMENTS_DIR}"
        )

    chunker = MarkdownChunker(
        chunk_size_words=180,
        overlap_words=30,
    )

    chunks = chunker.chunk_documents(documents)

    if not chunks:
        raise RuntimeError(
            "Los documentos no generaron ningún chunk."
        )

    embedding_provider = OpenAIEmbeddingProvider()
    vector_store = ChromaVectorStore()

    if reset:
        vector_store.reset()

    processed_chunks = 0

    for start in range(
        0,
        len(chunks),
        batch_size,
    ):
        batch = chunks[start:start + batch_size]

        embeddings = embedding_provider.embed_texts(
            [chunk.text for chunk in batch]
        )

        vector_store.upsert(
            chunks=batch,
            embeddings=embeddings,
        )

        processed_chunks += len(batch)

    return {
        "documents_loaded": len(documents),
        "chunks_generated": len(chunks),
        "chunks_processed": processed_chunks,
        "collection_count": vector_store.count(),
        "sources": [
            {
                "source": document.source,
                "title": document.title,
                "ecosystem": document.ecosystem,
                "source_url": document.source_url,
            }
            for document in documents
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Ingesta documentación técnica "
            "en la base vectorial."
        )
    )

    parser.add_argument(
        "--reset",
        action="store_true",
        help=(
            "Elimina la colección existente "
            "antes de volver a indexar."
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )

    args = parser.parse_args()

    result = ingest(
        reset=args.reset,
        batch_size=args.batch_size,
    )

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()