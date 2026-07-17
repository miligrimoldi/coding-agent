import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from dotenv import load_dotenv
from langfuse import (
    get_client,
    propagate_attributes,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parent

load_dotenv(
    dotenv_path=PROJECT_ROOT / ".env"
)


class NoOpObservation:
    """
    Observación vacía utilizada cuando Langfuse no está configurado.

    De esta manera, los tests y el agente pueden ejecutarse sin
    credenciales de observabilidad.
    """

    def update(
        self,
        **kwargs: Any,
    ) -> None:
        return None


class Observability:
    MAX_STRING_LENGTH = 4000
    MAX_COLLECTION_ITEMS = 30

    def __init__(self) -> None:
        self.enabled = bool(
            os.getenv(
                "LANGFUSE_PUBLIC_KEY"
            )
            and os.getenv(
                "LANGFUSE_SECRET_KEY"
            )
            and os.getenv(
                "LANGFUSE_BASE_URL"
            )
        )

        self.client = (
            get_client()
            if self.enabled
            else None
        )

    @contextmanager
    def run_span(
        self,
        *,
        user_request: str,
        workspace_path: str,
        request_mode: str,
    ) -> Iterator[Any]:
        """
        Crea la observación raíz de una ejecución completa.

        Todas las generaciones OpenAI, tools y spans de subagentes
        creados dentro de este contexto quedarán anidados.
        """

        if (
            not self.enabled
            or self.client is None
        ):
            yield NoOpObservation()
            return

        workspace_name = Path(
            workspace_path
        ).name

        project_session_id = (
            self._project_session_id(
                workspace_path
            )
        )

        with (
            self.client
            .start_as_current_observation(
                as_type="span",
                name="coding-agent-run",
                input={
                    "user_request": (
                        user_request
                    ),
                    "workspace": (
                        workspace_name
                    ),
                    "request_mode": (
                        request_mode
                    ),
                },
            )
        ) as observation:
            # En Langfuse v4 estos atributos se propagan a la
            # observación raíz y a todas sus observaciones hijas.
            with propagate_attributes(
                trace_name=(
                    "coding-agent-run"
                ),
                session_id=(
                    project_session_id
                ),
                tags=[
                    "coding-agent",
                    request_mode,
                ],
                metadata={
                    "workspace": (
                        workspace_name
                    ),
                    "requestmode": (
                        request_mode
                    ),
                },
            ):
                try:
                    yield observation

                except Exception as exc:
                    observation.update(
                        level="ERROR",
                        status_message=str(
                            exc
                        ),
                        output={
                            "status": "error",
                            "error_type": (
                                type(
                                    exc
                                ).__name__
                            ),
                            "error": str(exc),
                        },
                    )

                    raise

    @contextmanager
    def subagent_span(
        self,
        *,
        subagent: str,
        phase: str,
        request_mode: str,
    ) -> Iterator[Any]:
        """
        Registra una ejecución completa de un subagente.

        Las llamadas al LLM y las tools ejecutadas dentro de este
        contexto quedarán como observaciones hijas.
        """

        if (
            not self.enabled
            or self.client is None
        ):
            yield NoOpObservation()
            return

        with (
            self.client
            .start_as_current_observation(
                as_type="span",
                name=(
                    f"subagent:{subagent}"
                ),
                input={
                    "subagent": subagent,
                    "phase": phase,
                    "request_mode": (
                        request_mode
                    ),
                },
                metadata={
                    "subagent": subagent,
                    "phase": phase,
                },
            )
        ) as observation:
            try:
                yield observation

            except Exception as exc:
                observation.update(
                    level="ERROR",
                    status_message=str(
                        exc
                    ),
                    output={
                        "status": "error",
                        "error_type": (
                            type(
                                exc
                            ).__name__
                        ),
                        "error": str(exc),
                    },
                )

                raise

    @contextmanager
    def tool_span(
        self,
        *,
        subagent: str,
        tool_name: str,
        arguments: dict,
    ) -> Iterator[Any]:
        """
        Registra una tool call.

        Se sanitizan los argumentos para evitar enviar archivos
        completos o contenidos excesivamente largos a Langfuse.
        """

        if (
            not self.enabled
            or self.client is None
        ):
            yield NoOpObservation()
            return

        safe_arguments = (
            self.sanitize_tool_arguments(
                tool_name=tool_name,
                arguments=arguments,
            )
        )

        with (
            self.client
            .start_as_current_observation(
                as_type="tool",
                name=f"tool:{tool_name}",
                input={
                    "subagent": subagent,
                    "tool": tool_name,
                    "arguments": (
                        safe_arguments
                    ),
                },
                metadata={
                    "subagent": subagent,
                    "tool": tool_name,
                },
            )
        ) as observation:
            try:
                yield observation

            except Exception as exc:
                observation.update(
                    level="ERROR",
                    status_message=str(
                        exc
                    ),
                    output={
                        "status": "error",
                        "error_type": (
                            type(
                                exc
                            ).__name__
                        ),
                        "error": str(exc),
                    },
                )

                raise

    def build_run_output(
        self,
        task_state: Any,
    ) -> dict:
        """
        Construye el resultado final que se mostrará en la
        observación raíz.
        """

        return {
            "status": getattr(
                task_state,
                "status",
                "unknown",
            ),
            "current_phase": getattr(
                task_state,
                "current_phase",
                "",
            ),
            "sources_consulted": list(
                getattr(
                    task_state,
                    "sources_consulted",
                    [],
                )
            ),
            "files_modified": list(
                getattr(
                    task_state,
                    "files_modified",
                    [],
                )
            ),
            "iterations_by_subagent": dict(
                getattr(
                    task_state,
                    "iterations_by_subagent",
                    {},
                )
            ),
            "observations": list(
                getattr(
                    task_state,
                    "observations",
                    [],
                )
            ),
            "subagents_executed": list(
                getattr(
                    task_state,
                    "subagent_results",
                    {},
                ).keys()
            ),
        }

    def build_subagent_output(
        self,
        result: Any,
        task_state: Any,
    ) -> dict:
        """
        Resume el resultado de un subagente sin enviar el TaskState
        completo.
        """

        subagent_name = getattr(
            result,
            "subagent",
            "",
        )

        iterations = getattr(
            task_state,
            "iterations_by_subagent",
            {},
        ).get(
            subagent_name
        )

        return {
            "subagent": subagent_name,
            "summary": getattr(
                result,
                "summary",
                "",
            ),
            "sources": list(
                getattr(
                    result,
                    "sources",
                    [],
                )
            ),
            "iterations": iterations,
            "data": self.sanitize_value(
                getattr(
                    result,
                    "data",
                    {},
                )
            ),
        }

    def build_tool_output(
        self,
        *,
        tool_name: str,
        result: Any,
        outcome: Optional[str] = None,
        duration_ms: Optional[
            float
        ] = None,
    ) -> dict:
        """
        Convierte el output de una tool en una estructura útil para
        Langfuse.

        Para RAG y web conserva las fuentes recuperadas. Para lectura
        de archivos evita enviar el archivo completo.
        """

        result_text = str(result)

        output: dict[str, Any] = {
            "outcome": (
                outcome or "unknown"
            ),
            "duration_ms": duration_ms,
        }

        if tool_name in {
            "rag_search",
            "web_search",
        }:
            try:
                parsed = json.loads(
                    result_text
                )

                output["result"] = (
                    self.sanitize_value(
                        parsed
                    )
                )

            except json.JSONDecodeError:
                output["result"] = (
                    self._truncate(
                        result_text
                    )
                )

            return output

        if tool_name == "read_file":
            output.update({
                "success": (
                    not result_text.startswith(
                        "Error"
                    )
                ),
                "characters_read": len(
                    result_text
                ),
                "preview": self._truncate(
                    result_text,
                    limit=500,
                ),
            })

            return output

        if tool_name == "list_files":
            entries = [
                line
                for line
                in result_text.splitlines()
                if line.strip()
            ]

            output.update({
                "entry_count": len(entries),
                "entries": entries[
                    :self.MAX_COLLECTION_ITEMS
                ],
            })

            return output

        output["result"] = (
            self._truncate(
                result_text
            )
        )

        return output

    def sanitize_tool_arguments(
        self,
        *,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        """
        Evita enviar a Langfuse el contenido completo escrito por
        write_file o comandos excesivamente largos.
        """

        safe_arguments = dict(
            arguments or {}
        )

        if (
            tool_name == "write_file"
            and isinstance(
                safe_arguments.get(
                    "content"
                ),
                str,
            )
        ):
            content = safe_arguments[
                "content"
            ]

            safe_arguments[
                "content"
            ] = {
                "characters": len(
                    content
                ),
                "preview": self._truncate(
                    content,
                    limit=600,
                ),
            }

        if (
            tool_name == "run_command"
            and isinstance(
                safe_arguments.get(
                    "command"
                ),
                str,
            )
        ):
            safe_arguments[
                "command"
            ] = self._truncate(
                safe_arguments[
                    "command"
                ],
                limit=1000,
            )

        return self.sanitize_value(
            safe_arguments
        )

    def sanitize_value(
        self,
        value: Any,
        *,
        depth: int = 0,
    ) -> Any:
        """
        Limita profundidad, tamaño de strings y cantidad de elementos
        antes de enviar datos a observabilidad.
        """

        if depth >= 6:
            return (
                "<maximum-depth-reached>"
            )

        if isinstance(value, str):
            return self._truncate(
                value
            )

        if value is None or isinstance(
            value,
            (
                bool,
                int,
                float,
            ),
        ):
            return value

        if isinstance(value, dict):
            limited_items = list(
                value.items()
            )[
                :self.MAX_COLLECTION_ITEMS
            ]

            result = {
                str(key): self.sanitize_value(
                    item,
                    depth=depth + 1,
                )
                for key, item
                in limited_items
            }

            if (
                len(value)
                > self.MAX_COLLECTION_ITEMS
            ):
                result[
                    "_truncated_items"
                ] = (
                    len(value)
                    - self.MAX_COLLECTION_ITEMS
                )

            return result

        if isinstance(
            value,
            (
                list,
                tuple,
                set,
            ),
        ):
            items = list(value)

            result = [
                self.sanitize_value(
                    item,
                    depth=depth + 1,
                )
                for item
                in items[
                    :self.MAX_COLLECTION_ITEMS
                ]
            ]

            if (
                len(items)
                > self.MAX_COLLECTION_ITEMS
            ):
                result.append({
                    "_truncated_items": (
                        len(items)
                        - self.MAX_COLLECTION_ITEMS
                    )
                })

            return result

        return self._truncate(
            str(value)
        )

    def flush(self) -> None:
        if (
            self.enabled
            and self.client is not None
        ):
            self.client.flush()

    @staticmethod
    def _project_session_id(
        workspace_path: str,
    ) -> str:
        normalized = str(
            Path(
                workspace_path
            ).resolve()
        )

        digest = hashlib.sha256(
            normalized.encode(
                "utf-8"
            )
        ).hexdigest()[:16]

        return f"project-{digest}"

    def _truncate(
        self,
        value: str,
        *,
        limit: Optional[int] = None,
    ) -> str:
        effective_limit = (
            limit
            or self.MAX_STRING_LENGTH
        )

        if (
            len(value)
            <= effective_limit
        ):
            return value

        remaining = (
            len(value)
            - effective_limit
        )

        return (
            value[:effective_limit]
            + "\n"
            + (
                f"<truncated {remaining} "
                "characters>"
            )
        )


_observability = Observability()


def get_observability() -> Observability:
    return _observability