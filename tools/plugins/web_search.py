import json
import os
from typing import Optional

from tools.base import Tool


def _execute(
    query: str,
    domains: Optional[list[str]] = None,
) -> str:
    try:
        from tavily import TavilyClient
    except ImportError:
        return json.dumps({
            "query": query,
            "results": [],
            "error": (
                "Falta instalar tavily-python."
            ),
        }, ensure_ascii=False)

    api_key = os.environ.get("TAVILY_API_KEY")

    if not api_key:
        return json.dumps({
            "query": query,
            "results": [],
            "error": (
                "Falta la variable TAVILY_API_KEY."
            ),
        }, ensure_ascii=False)

    try:
        client = TavilyClient(api_key=api_key)

        response = client.search(
            query=query,
            search_depth="basic",
            max_results=5,
            include_domains=domains or [],
        )

        results = [
            {
                "title": item.get(
                    "title",
                    "Sin título",
                ),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
                "score": item.get("score"),
            }
            for item in response.get("results", [])
        ]

        return json.dumps({
            "query": query,
            "domains": domains or [],
            "results": results,
            "response_time": response.get(
                "response_time"
            ),
        }, ensure_ascii=False)

    except Exception as exc:
        return json.dumps({
            "query": query,
            "domains": domains or [],
            "results": [],
            "error": str(exc),
        }, ensure_ascii=False)


TOOL = Tool(
    name="web_search",
    description=(
        "Busca información técnica en la web. Debe utilizarse "
        "solamente cuando el RAG no aporta evidencia suficiente."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
            },
            "domains": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": (
                    "Dominios oficiales permitidos para la búsqueda."
                ),
            },
        },
        "required": ["query"],
    },
    execute=_execute,
    category="network",
)