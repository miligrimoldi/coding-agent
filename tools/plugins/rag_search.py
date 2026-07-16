import json

from rag.retriever import Retriever
from tools.base import Tool
from typing import Optional


def _execute(
    query: str,
    n_results: int = 5,
    ecosystem: Optional[str] = None,
) -> str:
    try:
        retriever = Retriever()

        result = retriever.search(
            query=query,
            n_results=n_results,
            ecosystem=ecosystem,
        )

        return json.dumps(
            result,
            ensure_ascii=False,
        )

    except Exception as exc:
        return json.dumps({
            "query": query,
            "results": [],
            "result_count": 0,
            "evidence_sufficient": False,
            "error": str(exc),
        }, ensure_ascii=False)


TOOL = Tool(
    name="rag_search",
    description=(
        "Busca primero en la base RAG de documentación técnica "
        "y devuelve fragmentos, metadata, fuentes y similitud."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
            },
            "n_results": {
                "type": "integer",
                "minimum": 1,
                "maximum": 10,
                "default": 5,
            },
            "ecosystem": {
                "type": "string",
                "description": (
                    "Filtro opcional: nestjs, prisma o jest."
                ),
            },
        },
        "required": ["query"],
    },
    execute=_execute,
    category="network",
)