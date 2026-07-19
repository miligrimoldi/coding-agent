import json
import os
from typing import Optional
from urllib.parse import urlparse

from tools.base import Tool


def _is_allowed_url(
    url: str,
    domains: Optional[list[str]],
) -> bool:
    if not domains:
        return True

    if not isinstance(url, str) or not url.strip():
        return False

    hostname = (
        urlparse(url).hostname or ""
    ).lower()

    normalized_domains = [
        domain.strip().lower().lstrip(".")
        for domain in domains
        if isinstance(domain, str) and domain.strip()
    ]

    return any(
        hostname == domain
        or hostname.endswith(f".{domain}")
        for domain in normalized_domains
    )


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

        raw_results = response.get(
            "results",
            [],
        )

        # Cuántos resultados devolvió Tavily antes de aplicar nuestro
        # propio filtro de dominio -- permite distinguir "Tavily no
        # encontró nada" de "encontró algo pero no era de un dominio
        # oficial", en vez de que ambos casos colapsen en una lista vacía
        # sin explicación.
        raw_result_count = len(raw_results)

        results = [
            {
                "title": item.get(
                    "title",
                    "Sin título",
                ),
                "url": item.get(
                    "url",
                    "",
                ),
                "content": item.get(
                    "content",
                    "",
                ),
                "score": item.get(
                    "score",
                ),
            }
            for item in raw_results
            if _is_allowed_url(
                item.get("url", ""),
                domains,
            )
        ]

        return json.dumps({
            "query": query,
            "domains": domains or [],
            "results": results,
            "raw_result_count": raw_result_count,
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