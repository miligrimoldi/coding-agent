import os

from tools.base import Tool


def _execute(query: str) -> str:
    try:
        from tavily import TavilyClient
    except ImportError:
        return "Error: falta instalar tavily-python (pip install tavily-python)."

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: falta la variable de entorno TAVILY_API_KEY."

    try:
        client = TavilyClient(api_key=api_key)
        response = client.search(query=query, search_depth="basic", max_results=5)
        results = []
        for item in response.get("results", []):
            title = item.get("title", "No title")
            url = item.get("url", "")
            content = item.get("content", "")
            results.append(f"TITLE: {title}\nURL: {url}\nCONTENT: {content}\n")
        return "\n---\n".join(results) if results else "No web results found."
    except Exception as e:
        return f"Web search error: {e}"


TOOL = Tool(
    name="web_search",
    description="Busca en la web y devuelve resultados relevantes.",
    parameters={
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
    execute=_execute,
    category="network",
)