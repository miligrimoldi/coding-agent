import json
import re
from pathlib import Path
from typing import Optional

from llm_client import get_client, MODEL
from request_mode import (
    RequestMode,
    detect_request_mode,
)
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor


_REQUEST_TOKEN_PATTERN = re.compile(
    r"[a-záéíóúüñ0-9_-]+"
)


class Researcher:
    ALLOWED_TOOLS = [
        "read_file",
        "rag_search",
        "web_search",
    ]

    # El Researcher no vuelve a explorar todo el repositorio.
    # Solo puede verificar puntualmente hasta tres archivos que
    # ya fueron identificados por el Explorer.
    MAX_VERIFICATION_FILES = 3
    MAX_FILE_CONTENT_CHARS = 6000

    OFFICIAL_DOMAINS_BY_ECOSYSTEM = {
        "nestjs": [
            "docs.nestjs.com",
        ],
        "prisma": [
            "prisma.io",
        ],
        "jest": [
            "jestjs.io",
        ],
    }

    SYSTEM_PROMPT = """
Sos el subagente Researcher dentro de un sistema multiagente de desarrollo
de código.

Tu responsabilidad es investigar y producir recomendaciones técnicas
basadas en:
- evidencia verificada por el Explorer;
- verificaciones puntuales de archivos concretos;
- documentación recuperada mediante RAG;
- web oficial solamente cuando la evidencia anterior no alcanza.

La exploración principal del repositorio corresponde al Explorer. No debés
volver a explorar el proyecto desde cero.

Recibís:
- original_request;
- task_mode: analysis o implementation;
- explorer_findings;
- repository_verifications;
- rag_results;
- eventualmente web_results.

Reglas generales:
- Basá tus conclusiones en evidencia.
- Diferenciá repositorio, memoria, RAG, web e inferencias.
- No implementes código.
- No inventes APIs, decorators, archivos, comandos ni convenciones.
- Una descripción del comportamiento actual puede citar paths verificados
  del repositorio.
- Una recomendación de API, decorator, módulo o patrón técnico debe incluir
  un chunk_id o una URL en evidence.
- Si una recomendación concreta no tiene respaldo, movela a inferences o
  risks_or_unknowns.
- El RAG debe consultarse antes que la web.
- needs_web_fallback debe ser true solo cuando repositorio y RAG no alcanzan
  para respaldar el tema técnico central.
- No actives web únicamente porque existe una pregunta funcional abierta.
- Respondé con un único objeto JSON sin texto alrededor.

Para task_mode=analysis:
- Describí primero la implementación actual.
- Después presentá mejoras posibles.
- Las decisiones necesarias para implementar una mejora futura no bloquean
  el análisis.
- requirements_clear debe ser true.
- clarifications_needed debe ser una lista vacía.
- Las preguntas abiertas deben ir en risks_or_unknowns.
- No conviertas una recomendación hipotética en requisito obligatorio.

Para task_mode=implementation:
- evidence_sufficient indica si existe evidencia técnica suficiente para
  orientar la implementación.
- requirements_clear indica si están definidas las decisiones funcionales
  necesarias para modificar el repositorio de forma segura.
- Para operaciones destructivas o automáticas, no supongas períodos,
  frecuencias, políticas de retención, cascadas, auditoría ni tipo de
  borrado.
- Si faltan decisiones funcionales necesarias, marcá
  requirements_clear=false y enumeralas en clarifications_needed.

Formato:
{
  "task_mode": "analysis|implementation",
  "evidence_sufficient": true,
  "requirements_clear": true,
  "clarifications_needed": [],
  "needs_web_fallback": false,
  "used_web_fallback": false,
  "current_implementation": [
    {
      "aspect": "...",
      "description": "...",
      "evidence": ["path del repositorio"]
    }
  ],
  "suggested_improvements": [
    {
      "topic": "...",
      "recommendation": "...",
      "priority": "low|medium|high",
      "evidence": ["path, chunk_id o URL"]
    }
  ],
  "findings": [
    {
      "topic": "...",
      "recommendation": "...",
      "evidence": ["path, chunk_id o URL"]
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
        task_state.set_phase(
            "research"
        )

        explorer_result = (
            task_state.last_result_of(
                "explorer"
            )
        )

        if explorer_result is None:
            task_state.status = "needs_help"

            return SubagentResult(
                subagent="researcher",
                summary=(
                    "No se pudo investigar porque "
                    "falta el resultado del Explorer."
                ),
                data={
                    "evidence_sufficient": False,
                    "requirements_clear": False,
                    "clarifications_needed": [],
                    "reason": (
                        "missing_explorer_result"
                    ),
                },
                sources=[],
            )

        task_mode = detect_request_mode(
            task_state.original_request
        )

        repository_verifications = (
            self._verify_repository_context(
                original_request=(
                    task_state.original_request
                ),
                explorer_data=(
                    explorer_result.data
                ),
                task_state=task_state,
            )
        )

        research_query = self._build_query(
            original_request=(
                task_state.original_request
            ),
            explorer_data=(
                explorer_result.data
            ),
            task_mode=task_mode.value,
        )

        ecosystems = self._detect_ecosystems(
            original_request=(
                task_state.original_request
            ),
            explorer_data=(
                explorer_result.data
            ),
        )

        rag_data = self._search_rag(
            query=research_query,
            ecosystems=ecosystems,
            task_state=task_state,
        )

        web_data = {
            "results": [],
        }

        used_web_fallback = False
        synthesis_iterations = 1

        synthesized_data = self._synthesize(
            task_state=task_state,
            task_mode=task_mode.value,
            explorer_data=(
                explorer_result.data
            ),
            repository_verifications=(
                repository_verifications
            ),
            rag_data=rag_data,
            web_data=web_data,
            used_web_fallback=False,
        )

        needs_web_fallback = bool(
            synthesized_data.get(
                "needs_web_fallback",
                False,
            )
            or not synthesized_data.get(
                "evidence_sufficient",
                False,
            )
        )

        if needs_web_fallback:
            used_web_fallback = True
            synthesis_iterations += 1

            web_data = self._run_web_fallback(
                query=research_query,
                ecosystems=ecosystems,
                task_state=task_state,
            )

            synthesized_data = self._synthesize(
                task_state=task_state,
                task_mode=task_mode.value,
                explorer_data=(
                    explorer_result.data
                ),
                repository_verifications=(
                    repository_verifications
                ),
                rag_data=rag_data,
                web_data=web_data,
                used_web_fallback=True,
            )

        if task_mode == RequestMode.ANALYSIS:
            synthesized_data = (
                self._normalize_analysis_result(
                    synthesized_data
                )
            )
        else:
            synthesized_data = (
                self._normalize_implementation_result(
                    synthesized_data
                )
            )

        synthesized_data["task_mode"] = (
            task_mode.value
        )

        synthesized_data[
            "research_query"
        ] = research_query

        synthesized_data[
            "used_web_fallback"
        ] = used_web_fallback

        synthesized_data[
            "needs_web_fallback"
        ] = False

        synthesized_data[
            "ecosystems_searched"
        ] = ecosystems

        synthesized_data[
            "missing_rag_evidence_for"
        ] = rag_data.get(
            "missing_evidence_for",
            [],
        )

        synthesized_data["rag_sources"] = (
            self._extract_rag_sources(
                rag_data
            )
        )

        synthesized_data["web_sources"] = (
            web_data.get(
                "results",
                [],
            )
        )

        synthesized_data[
            "repository_files_verified"
        ] = [
            item["path"]
            for item in repository_verifications
        ]

        task_state.record_iterations(
            "researcher",
            synthesis_iterations,
        )

        sources = [
            "repository",
            "rag",
        ]

        if used_web_fallback:
            sources.append(
                "web"
            )

        if task_mode == RequestMode.ANALYSIS:
            summary_prefix = (
                "Análisis técnico completado"
            )
        else:
            summary_prefix = (
                "Investigación técnica completada"
            )

        summary = (
            f"{summary_prefix} con fallback web."
            if used_web_fallback
            else (
                f"{summary_prefix} usando "
                "repositorio y RAG."
            )
        )

        return SubagentResult(
            subagent="researcher",
            summary=summary,
            data=synthesized_data,
            sources=sources,
        )

    def _verify_repository_context(
        self,
        *,
        original_request: str,
        explorer_data: dict,
        task_state: TaskState,
    ) -> list[dict]:
        """
        Lee como máximo tres archivos concretos.

        Solo considera paths identificados por el Explorer y que todavía
        no fueron incluidos entre archivos_leidos.
        """

        relevant_files = explorer_data.get(
            "archivos_relevantes",
            [],
        )

        already_read = set(
            explorer_data.get(
                "archivos_leidos",
                [],
            )
        )

        if not isinstance(
            relevant_files,
            list,
        ):
            return []

        request_tokens = {
            token
            for token in (
                _REQUEST_TOKEN_PATTERN.findall(
                    original_request.lower()
                )
            )
            if len(token) >= 4
        }

        ranked_candidates: list[
            tuple[int, int, str]
        ] = []

        seen: set[str] = set()

        for index, raw_path in enumerate(
            relevant_files
        ):
            if not isinstance(
                raw_path,
                str,
            ):
                continue

            path = (
                raw_path
                .replace("\\", "/")
                .strip()
                .strip("/")
            )

            if (
                not path
                or path in seen
                or path in already_read
                or not self._is_readable_file(
                    path
                )
            ):
                continue

            seen.add(path)

            lower_path = path.lower()
            filename = Path(
                lower_path
            ).name

            score = 0

            for token in request_tokens:
                if token in lower_path:
                    score += 4

            if "controller" in filename:
                score += 6

            if "service" in filename:
                score += 6

            if "dto" in filename:
                score += 6

            if filename == "main.ts":
                score += 5

            if filename == "schema.prisma":
                score += 6

            if ".spec." in filename:
                score += 4

            ranked_candidates.append(
                (
                    -score,
                    index,
                    path,
                )
            )

        ranked_candidates.sort()

        verifications: list[dict] = []

        for _, _, path in ranked_candidates[
            :self.MAX_VERIFICATION_FILES
        ]:
            output = self.tool_executor.execute(
                subagent="researcher",
                tool_name="read_file",
                arguments={
                    "path": path,
                },
                task_state=task_state,
                allowed_tools=self.ALLOWED_TOOLS,
            )

            output_text = str(output)

            if output_text.startswith(
                "Error"
            ):
                task_state.record_observation(
                    "Researcher no pudo verificar "
                    f"{path}: {output_text}"
                )

                continue

            verifications.append({
                "path": path,
                "content": output_text[
                    :self.MAX_FILE_CONTENT_CHARS
                ],
                "truncated": (
                    len(output_text)
                    > self.MAX_FILE_CONTENT_CHARS
                ),
            })

        return verifications

    @staticmethod
    def _is_readable_file(
        path: str,
    ) -> bool:
        lower_path = path.lower()

        forbidden_parts = (
            "node_modules/",
            ".git/",
            "dist/",
            "coverage/",
            "src/generated/",
        )

        if any(
            part in lower_path
            for part in forbidden_parts
        ):
            return False

        valid_suffixes = (
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".json",
            ".prisma",
            ".yaml",
            ".yml",
            ".md",
            ".txt",
        )

        return lower_path.endswith(
            valid_suffixes
        )

    def _search_rag(
        self,
        *,
        query: str,
        ecosystems: list[str],
        task_state: TaskState,
    ) -> dict:
        ecosystems_to_search = (
            ecosystems or [None]
        )

        results_by_ecosystem: dict = {}
        combined_results: list[dict] = []
        missing_evidence_for: list[str] = []

        for ecosystem in ecosystems_to_search:
            arguments = {
                "query": query,
                "n_results": 4,
            }

            if ecosystem is not None:
                arguments[
                    "ecosystem"
                ] = ecosystem

            rag_output = (
                self.tool_executor.execute(
                    subagent="researcher",
                    tool_name="rag_search",
                    arguments=arguments,
                    task_state=task_state,
                    allowed_tools=(
                        self.ALLOWED_TOOLS
                    ),
                )
            )

            result = self._parse_json_result(
                str(rag_output)
            )

            key = ecosystem or "all"

            results_by_ecosystem[key] = result

            if not result.get(
                "evidence_sufficient",
                False,
            ):
                missing_evidence_for.append(
                    key
                )

            combined_results.extend(
                result.get(
                    "results",
                    [],
                )
            )

        unique_results: dict[str, dict] = {}

        for result in combined_results:
            chunk_id = result.get(
                "chunk_id"
            )

            if not chunk_id:
                continue

            previous = unique_results.get(
                chunk_id
            )

            if (
                previous is None
                or result.get(
                    "similarity",
                    0,
                )
                > previous.get(
                    "similarity",
                    0,
                )
            ):
                unique_results[
                    chunk_id
                ] = result

        ordered_results = sorted(
            unique_results.values(),
            key=lambda item: item.get(
                "similarity",
                0,
            ),
            reverse=True,
        )

        # No se considera insuficiente todo el RAG únicamente porque
        # falte evidencia para un ecosistema secundario.
        evidence_sufficient = any(
            result.get(
                "evidence_sufficient",
                False,
            )
            for result in (
                results_by_ecosystem.values()
            )
        )

        return {
            "query": query,
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
        ecosystems: list[str],
        task_state: TaskState,
    ) -> dict:
        domains: list[str] = []

        for ecosystem in ecosystems:
            domains.extend(
                self.OFFICIAL_DOMAINS_BY_ECOSYSTEM.get(
                    ecosystem,
                    [],
                )
            )

        domains = list(
            dict.fromkeys(
                domains
            )
        )

        if not domains:
            domains = [
                "docs.nestjs.com",
                "prisma.io",
                "jestjs.io",
            ]

        output = self.tool_executor.execute(
            subagent="researcher",
            tool_name="web_search",
            arguments={
                "query": query,
                "domains": domains,
            },
            task_state=task_state,
            allowed_tools=self.ALLOWED_TOOLS,
        )

        return self._parse_json_result(
            str(output)
        )

    def _synthesize(
        self,
        *,
        task_state: TaskState,
        task_mode: str,
        explorer_data: dict,
        repository_verifications: list[dict],
        rag_data: dict,
        web_data: dict,
        used_web_fallback: bool,
    ) -> dict:
        client = get_client()

        context = {
            "original_request": (
                task_state.original_request
            ),
            "task_mode": task_mode,
            "explorer_findings": (
                explorer_data
            ),
            "repository_verifications": (
                repository_verifications
            ),
            "rag_results": rag_data,
            "web_results": web_data,
            "used_web_fallback": (
                used_web_fallback
            ),
        }

        response = (
            client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            self.SYSTEM_PROMPT
                        ),
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
        )

        content = (
            response.choices[0].message.content
        )

        try:
            parsed = json.loads(
                content or ""
            )

            if isinstance(parsed, dict):
                return parsed

            raise TypeError(
                "La salida no es un objeto."
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            task_state.record_observation(
                "Researcher no devolvió JSON "
                "válido; se guardó como texto libre."
            )

            return {
                "task_mode": task_mode,
                "evidence_sufficient": False,
                "requirements_clear": (
                    task_mode == "analysis"
                ),
                "clarifications_needed": [],
                "needs_web_fallback": (
                    not used_web_fallback
                ),
                "resumen_libre": content,
                "current_implementation": [],
                "suggested_improvements": [],
                "findings": [],
                "repository_context": [],
                "inferences": [],
                "risks_or_unknowns": [
                    "La salida no respetó el "
                    "formato JSON esperado."
                ],
            }

    @staticmethod
    def _normalize_analysis_result(
        data: dict,
    ) -> dict:
        if not isinstance(data, dict):
            data = {}

        clarifications = data.get(
            "clarifications_needed",
            [],
        )

        if not isinstance(
            clarifications,
            list,
        ):
            clarifications = []

        risks = data.get(
            "risks_or_unknowns",
            [],
        )

        if not isinstance(risks, list):
            risks = []

        for clarification in clarifications:
            if not clarification:
                continue

            text = (
                "Pregunta abierta no bloqueante "
                "para una futura implementación: "
                f"{clarification}"
            )

            if text not in risks:
                risks.append(text)

        data["task_mode"] = "analysis"
        data["requirements_clear"] = True
        data["clarifications_needed"] = []
        data["risks_or_unknowns"] = risks

        Researcher._normalize_lists(data)

        return data

    @staticmethod
    def _normalize_implementation_result(
        data: dict,
    ) -> dict:
        if not isinstance(data, dict):
            data = {}

        data["task_mode"] = (
            "implementation"
        )

        if not isinstance(
            data.get(
                "clarifications_needed"
            ),
            list,
        ):
            data[
                "clarifications_needed"
            ] = []

        if not isinstance(
            data.get(
                "risks_or_unknowns"
            ),
            list,
        ):
            data[
                "risks_or_unknowns"
            ] = []

        Researcher._normalize_lists(data)

        return data

    @staticmethod
    def _normalize_lists(
        data: dict,
    ) -> None:
        for field_name in (
            "current_implementation",
            "suggested_improvements",
            "findings",
            "repository_context",
            "rag_sources",
            "web_sources",
            "inferences",
        ):
            if not isinstance(
                data.get(field_name),
                list,
            ):
                data[field_name] = []

    @staticmethod
    def _build_query(
        *,
        original_request: str,
        explorer_data: dict,
        task_mode: str,
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

        if not isinstance(
            dependencies,
            list,
        ):
            dependencies = []

        if not isinstance(
            relevant_files,
            list,
        ):
            relevant_files = []

        file_names = [
            Path(path).name
            for path in relevant_files[:10]
            if isinstance(path, str)
        ]

        query_parts = [
            original_request,
            f"task mode: {task_mode}",
            str(language),
            str(framework),
            " ".join(
                str(item)
                for item in dependencies[:12]
            ),
            " ".join(file_names),
        ]

        return " | ".join(
            part
            for part in query_parts
            if part
        )[:1400]

    @staticmethod
    def _detect_ecosystems(
        *,
        original_request: str,
        explorer_data: dict,
    ) -> list[str]:
        ecosystems: list[str] = []

        framework = str(
            explorer_data.get(
                "framework",
                "",
            )
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

        request = (
            original_request.lower()
        )

        if (
            "nest" in framework
            or any(
                "@nestjs/" in dependency
                for dependency in dependencies
            )
        ):
            ecosystems.append(
                "nestjs"
            )

        uses_prisma = bool(
            any(
                "prisma" in dependency
                for dependency in dependencies
            )
            or any(
                "schema.prisma" in path
                or "/prisma/" in path
                for path in relevant_files
            )
        )

        prisma_terms = (
            "prisma",
            "base de datos",
            "persistencia",
            "persistir",
            "guardar",
            "creación de ticket",
            "creacion de ticket",
            "modelo",
            "schema",
            "migración",
            "migracion",
            "enum",
            "filtro",
            "where",
            "eliminar",
            "borrar",
            "delete",
            "retención",
            "retencion",
            "viejo",
            "viejos",
        )

        if (
            uses_prisma
            and any(
                term in request
                for term in prisma_terms
            )
        ):
            ecosystems.append(
                "prisma"
            )

                has_test_files = any(
                    (
                        ".spec." in path
                        or ".test." in path
                        or path.startswith("test/")
                        or "/test/" in f"/{path}"
                        or path.startswith("tests/")
                        or "/tests/" in f"/{path}"
                    )
                    for path in relevant_files
                )

                uses_jest = bool(
                    any(
                        (
                            "jest" in dependency
                            or "@nestjs/testing"
                            in dependency
                        )
                        for dependency in dependencies
                    )
                    or has_test_files
                )

                testing_terms = (
                    "test",
                    "tests",
                    "testing",
                    "prueba",
                    "pruebas",
                    "e2e",
                    "spec",
                    "coverage",
                    "cobertura",
                    "mock",
                    "mocks",
                )

                has_testing_request = any(
                    term in request
                    for term in testing_terms
                )

                if (
                    uses_jest
                    and (
                        has_testing_request
                        or has_test_files
                    )
                ):
                    ecosystems.append(
                        "jest"
                    )

        return list(
            dict.fromkeys(
                ecosystems
            )
        )

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

            if not isinstance(
                metadata,
                dict,
            ):
                metadata = {}

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
                "evidence_sufficient": False,
                "error": (
                    "La tool no devolvió un "
                    "objeto JSON."
                ),
            }

        except json.JSONDecodeError:
            return {
                "results": [],
                "evidence_sufficient": False,
                "error": output,
            }