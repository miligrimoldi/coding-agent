import json
from pathlib import Path

from llm_client import get_client, MODEL
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from typing import Optional


class Researcher:
    ALLOWED_TOOLS = [
        "rag_search",
        "web_search",
    ]

    SYSTEM_PROMPT = """
Sos el subagente Researcher dentro de un sistema multiagente de
desarrollo de código.

Tu responsabilidad es investigar cómo debería resolverse técnicamente
el pedido del usuario.

Recibís:
- el pedido original;
- los hallazgos del Explorer;
- fragmentos recuperados del RAG;
- eventualmente resultados web oficiales.

Reglas:
- Basá tus recomendaciones en evidencia.
- Diferenciá información del repositorio, RAG, web e inferencias.
- No propongas modificar archivos que no fueron identificados o
  justificados.
- No implementes código.
- No inventes APIs, decorators, comandos ni convenciones.
- Respondé con un único JSON sin texto alrededor.

Formato:
{
  "evidence_sufficient": true,
  "used_web_fallback": false,
  "findings": [
    {
      "topic": "...",
      "recommendation": "...",
      "evidence": ["chunk_id o URL"]
    }
  ],
  "repository_context": [],
  "rag_sources": [],
  "web_sources": [],
  "inferences": [],
  "risks_or_unknowns": []
}
"""

    def __init__(
        self,
        tool_executor: ToolExecutor,
    ):
        self.tool_executor = tool_executor

    def run(
        self,
        task_state: TaskState,
    ) -> SubagentResult:
        task_state.set_phase("research")

        explorer_result = task_state.last_result_of(
            "explorer"
        )

        if explorer_result is None:
            task_state.status = "needs_help"

            return SubagentResult(
                subagent="researcher",
                summary=(
                    "No se pudo investigar porque falta "
                    "el resultado del Explorer."
                ),
                data={
                    "evidence_sufficient": False,
                    "reason": "missing_explorer_result",
                },
                sources=[],
            )

        research_query = self._build_query(
            original_request=task_state.original_request,
            explorer_data=explorer_result.data,
        )

        ecosystem = self._detect_ecosystem(
            explorer_result.data
        )

        rag_output = self.tool_executor.execute(
            subagent="researcher",
            tool_name="rag_search",
            arguments={
                "query": research_query,
                "n_results": 5,
                "ecosystem": ecosystem,
            },
            task_state=task_state,
            allowed_tools=self.ALLOWED_TOOLS,
        )

        rag_data = self._parse_json_result(
            rag_output
        )

        used_web_fallback = not rag_data.get(
            "evidence_sufficient",
            False,
        )

        web_data = {
            "results": [],
        }

        if used_web_fallback:
            web_data = self._run_web_fallback(
                query=research_query,
                task_state=task_state,
            )

        synthesized_data = self._synthesize(
            task_state=task_state,
            explorer_data=explorer_result.data,
            rag_data=rag_data,
            web_data=web_data,
            used_web_fallback=used_web_fallback,
        )

        synthesized_data["research_query"] = (
            research_query
        )

        synthesized_data["used_web_fallback"] = (
            used_web_fallback
        )

        synthesized_data.setdefault(
            "rag_sources",
            self._extract_rag_sources(rag_data),
        )

        synthesized_data.setdefault(
            "web_sources",
            web_data.get("results", []),
        )

        task_state.record_iterations(
            "researcher",
            1,
        )

        sources = [
            "repository",
            "rag",
        ]

        if used_web_fallback:
            sources.append("web")

        return SubagentResult(
            subagent="researcher",
            summary=(
                "Investigación técnica completada "
                f"{'con fallback web' if used_web_fallback else 'usando el RAG'}."
            ),
            data=synthesized_data,
            sources=sources,
        )

    def _run_web_fallback(
        self,
        *,
        query: str,
        task_state: TaskState,
    ) -> dict:
        output = self.tool_executor.execute(
            subagent="researcher",
            tool_name="web_search",
            arguments={
                "query": query,
                "domains": [
                    "docs.nestjs.com",
                    "prisma.io",
                    "jestjs.io",
                ],
            },
            task_state=task_state,
            allowed_tools=self.ALLOWED_TOOLS,
        )

        return self._parse_json_result(output)

    def _synthesize(
        self,
        *,
        task_state: TaskState,
        explorer_data: dict,
        rag_data: dict,
        web_data: dict,
        used_web_fallback: bool,
    ) -> dict:
        client = get_client()

        context = {
            "original_request": (
                task_state.original_request
            ),
            "repository_context": explorer_data,
            "rag_results": rag_data,
            "web_results": web_data,
            "used_web_fallback": used_web_fallback,
        }

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": self.SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        context,
                        ensure_ascii=False,
                    ),
                },
            ],
        )

        content = response.choices[0].message.content

        try:
            return json.loads(content)
        except (json.JSONDecodeError, TypeError):
            task_state.record_observation(
                "Researcher no devolvió JSON válido; "
                "se guardó la respuesta como texto libre."
            )

            return {
                "evidence_sufficient": False,
                "used_web_fallback": (
                    used_web_fallback
                ),
                "resumen_libre": content,
                "findings": [],
                "repository_context": [],
                "rag_sources": (
                    self._extract_rag_sources(
                        rag_data
                    )
                ),
                "web_sources": web_data.get(
                    "results",
                    [],
                ),
                "inferences": [],
                "risks_or_unknowns": [
                    "La salida no respetó el formato JSON."
                ],
            }

    @staticmethod
    def _build_query(
        *,
        original_request: str,
        explorer_data: dict,
    ) -> str:
        language = explorer_data.get(
            "lenguaje",
            "",
        )

        framework = explorer_data.get(
            "framework",
            "",
        )

        dependencies = explorer_data.get(
            "dependencias_detectadas",
            [],
        )

        relevant_files = explorer_data.get(
            "archivos_relevantes",
            [],
        )

        file_names = [
            Path(path).name
            for path in relevant_files[:8]
        ]

        query_parts = [
            original_request,
            language,
            framework,
            " ".join(dependencies[:10]),
            " ".join(file_names),
        ]

        return " | ".join(
            part
            for part in query_parts
            if part
        )[:1200]

    @staticmethod
    def _detect_ecosystem(
        explorer_data: dict,
    ) -> Optional[str]:
        framework = str(
            explorer_data.get("framework", "")
        ).lower()

        if "nest" in framework:
            return "nestjs"

        dependencies = [
            str(dependency).lower()
            for dependency in explorer_data.get(
                "dependencias_detectadas",
                [],
            )
        ]

        if any(
            "prisma" in dependency
            for dependency in dependencies
        ):
            return "prisma"

        return None

    @staticmethod
    def _extract_rag_sources(
        rag_data: dict,
    ) -> list[dict]:
        sources = []

        for result in rag_data.get(
            "results",
            [],
        ):
            metadata = result.get(
                "metadata",
                {},
            )

            sources.append({
                "chunk_id": result.get(
                    "chunk_id"
                ),
                "source": metadata.get(
                    "source"
                ),
                "title": metadata.get(
                    "title"
                ),
                "section": metadata.get(
                    "section"
                ),
                "source_url": metadata.get(
                    "source_url"
                ),
                "similarity": result.get(
                    "similarity"
                ),
            })

        return sources

    @staticmethod
    def _parse_json_result(
        output: str,
    ) -> dict:
        try:
            parsed = json.loads(output)

            if isinstance(parsed, dict):
                return parsed

            return {
                "results": [],
                "error": (
                    "La tool no devolvió un objeto JSON."
                ),
            }

        except json.JSONDecodeError:
            return {
                "results": [],
                "evidence_sufficient": False,
                "error": output,
            }