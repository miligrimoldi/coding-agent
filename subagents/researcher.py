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

        ecosystems = self._detect_ecosystems(
            original_request=task_state.original_request,
            explorer_data=explorer_result.data,
        )

        rag_data = self._search_rag(
            query=research_query,
            ecosystems=ecosystems,
            task_state=task_state,
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

        synthesized_data["ecosystems_searched"] = ecosystems
        synthesized_data["missing_rag_evidence_for"] = (
            rag_data.get("missing_evidence_for", [])
        )

        synthesized_data["rag_sources"] = (
            self._extract_rag_sources(rag_data)
        )

        synthesized_data["web_sources"] = (
            web_data.get("results", [])
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

    def _search_rag(
        self,
        *,
        query: str,
        ecosystems: list[str],
        task_state: TaskState,
    ) -> dict:
        """
        Ejecuta una búsqueda RAG por cada ecosistema relevante y combina
        los resultados.

        Si no se detectó ningún ecosistema, realiza una búsqueda global.
        """

        ecosystems_to_search = ecosystems or [None]

        results_by_ecosystem: dict = {}
        combined_results: list[dict] = []
        missing_evidence_for: list[str] = []

        for ecosystem in ecosystems_to_search:
            arguments = {
                "query": query,
                "n_results": 4,
            }

            if ecosystem is not None:
                arguments["ecosystem"] = ecosystem

            rag_output = self.tool_executor.execute(
                subagent="researcher",
                tool_name="rag_search",
                arguments=arguments,
                task_state=task_state,
                allowed_tools=self.ALLOWED_TOOLS,
            )

            result = self._parse_json_result(
                rag_output
            )

            ecosystem_key = ecosystem or "all"

            results_by_ecosystem[ecosystem_key] = result

            if not result.get(
                "evidence_sufficient",
                False,
            ):
                missing_evidence_for.append(
                    ecosystem_key
                )

            combined_results.extend(
                result.get("results", [])
            )

        # El mismo chunk podría aparecer en búsquedas diferentes.
        unique_results: dict[str, dict] = {}

        for result in combined_results:
            chunk_id = result.get("chunk_id")

            if not chunk_id:
                continue

            previous = unique_results.get(
                chunk_id
            )

            if (
                previous is None
                or result.get("similarity", 0)
                > previous.get("similarity", 0)
            ):
                unique_results[chunk_id] = result

        ordered_results = sorted(
            unique_results.values(),
            key=lambda item: item.get(
                "similarity",
                0,
            ),
            reverse=True,
        )

        evidence_sufficient = (
            len(missing_evidence_for) == 0
            and len(ordered_results) > 0
        )

        return {
            "query": query,
            "ecosystems_searched": [
                ecosystem or "all"
                for ecosystem in ecosystems_to_search
            ],
            "results_by_ecosystem": (
                results_by_ecosystem
            ),
            "results": ordered_results,
            "result_count": len(
                ordered_results
            ),
            "evidence_sufficient": (
                evidence_sufficient
            ),
            "missing_evidence_for": (
                missing_evidence_for
            ),
        }

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
    def _detect_ecosystems(
        *,
        original_request: str,
        explorer_data: dict,
    ) -> list[str]:
        """
        Detecta todos los ecosistemas relevantes para la tarea.

        No se limita al framework principal porque una misma funcionalidad
        puede requerir documentación de NestJS, Prisma y Jest.
        """

        ecosystems: list[str] = []

        framework = str(
            explorer_data.get("framework", "")
        ).lower()

        dependencies = [
            str(dependency).lower()
            for dependency in explorer_data.get(
                "dependencias_detectadas",
                [],
            )
        ]

        relevant_files = [
            str(path).lower()
            for path in explorer_data.get(
                "archivos_relevantes",
                [],
            )
        ]

        request = original_request.lower()

        # NestJS
        if (
            "nest" in framework
            or any("@nestjs/" in dependency for dependency in dependencies)
        ):
            ecosystems.append("nestjs")

        # Prisma
        prisma_request_terms = (
            "prisma",
            "base de datos",
            "persistencia",
            "modelo",
            "schema",
            "migración",
            "migracion",
            "enum",
            "filtro",
            "where",
        )

        uses_prisma = (
            any("prisma" in dependency for dependency in dependencies)
            or any("schema.prisma" in path for path in relevant_files)
        )

        request_needs_prisma = any(
            term in request
            for term in prisma_request_terms
        )

        if uses_prisma and request_needs_prisma:
            ecosystems.append("prisma")

        # Jest
        testing_terms = (
            "test",
            "tests",
            "testing",
            "prueba",
            "pruebas",
            "e2e",
        )

        uses_jest = any(
            "jest" in dependency
            for dependency in dependencies
        )

        request_needs_testing = any(
            term in request
            for term in testing_terms
        )

        if uses_jest and request_needs_testing:
            ecosystems.append("jest")

        # Evita duplicados manteniendo el orden.
        return list(dict.fromkeys(ecosystems))

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