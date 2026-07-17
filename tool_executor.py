import subprocess
import time
from pathlib import Path
from typing import Any, Collection, Optional

from observability import get_observability
from policy_engine import (
    PolicyEngine,
    PolicyViolation,
)
from task_state import TaskState
from tools.loader import get_tool


class ToolExecutor:
    def __init__(
        self,
        policy_engine: PolicyEngine,
        supervision_mode: bool = True,
    ):
        self.policy_engine = policy_engine
        self.supervision_mode = supervision_mode

    def execute(
        self,
        *,
        subagent: str,
        tool_name: str,
        arguments: dict,
        task_state: TaskState,
        allowed_tools: Optional[
            Collection[str]
        ] = None,
    ) -> str:
        """
        Ejecuta una tool después de aplicar:

        1. Permisos propios del subagente.
        2. Políticas globales.
        3. Aprobación humana, cuando corresponde.
        4. Registro de efectos sobre el workspace.
        5. Observabilidad en Langfuse.

        La observación de la tool queda anidada dentro del span del
        subagente que la invocó.
        """

        # Copia los argumentos para poder normalizarlos sin modificar
        # el diccionario original entregado por el subagente.
        arguments = dict(
            arguments or {}
        )

        # Para list_files, un path vacío representa la raíz del
        # workspace.
        if tool_name == "list_files":
            path_argument = arguments.get(
                "path"
            )

            if (
                not isinstance(
                    path_argument,
                    str,
                )
                or not path_argument.strip()
            ):
                arguments["path"] = "."

        observability = get_observability()

        with observability.tool_span(
            subagent=subagent,
            tool_name=tool_name,
            arguments=arguments,
        ) as tool_observation:
            approval_required = False
            approved_by_user: Optional[
                bool
            ] = None

            def finish(
                *,
                result: Any,
                outcome: str,
                duration_ms: Optional[
                    float
                ] = None,
                level: Optional[str] = None,
                status_message: Optional[
                    str
                ] = None,
            ) -> str:
                """
                Actualiza la observación de Langfuse antes de devolver
                el resultado al subagente.
                """

                result_text = str(result)

                update_arguments: dict[
                    str,
                    Any,
                ] = {
                    "output": (
                        observability
                        .build_tool_output(
                            tool_name=tool_name,
                            result=result_text,
                            outcome=outcome,
                            duration_ms=(
                                duration_ms
                            ),
                        )
                    ),
                    "metadata": {
                        "subagent": subagent,
                        "tool": tool_name,
                        "outcome": outcome,
                        "approvalrequired": (
                            approval_required
                        ),
                        "approvedbyuser": (
                            approved_by_user
                        ),
                    },
                }

                if level is not None:
                    update_arguments[
                        "level"
                    ] = level

                if status_message:
                    update_arguments[
                        "status_message"
                    ] = status_message

                tool_observation.update(
                    **update_arguments
                )

                return result_text

            # Control de permisos particulares del subagente.
            if (
                allowed_tools is not None
                and tool_name
                not in allowed_tools
            ):
                message = (
                    f"El subagente '{subagent}' "
                    "no tiene permitido usar la "
                    f"tool '{tool_name}'."
                )

                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome=(
                        "blocked_by_agent_permissions"
                    ),
                )

                task_state.record_observation(
                    message
                )

                return finish(
                    result=(
                        f"POLICY_BLOCKED: "
                        f"{message}"
                    ),
                    outcome=(
                        "blocked_by_agent_permissions"
                    ),
                    level="WARNING",
                    status_message=message,
                )

            # Obtención y validación de la tool.
            try:
                tool = get_tool(
                    tool_name
                )

                decision = (
                    self.policy_engine.validate(
                        tool=tool,
                        arguments=arguments,
                        workspace_path=(
                            task_state
                            .workspace_path
                        ),
                    )
                )

            except (
                ValueError,
                PolicyViolation,
            ) as exc:
                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome=(
                        "blocked_by_policy"
                    ),
                )

                task_state.record_observation(
                    str(exc)
                )

                return finish(
                    result=(
                        f"POLICY_BLOCKED: "
                        f"{exc}"
                    ),
                    outcome=(
                        "blocked_by_policy"
                    ),
                    level="WARNING",
                    status_message=str(exc),
                )

            approval_required = bool(
                decision.requires_approval
            )

            # Supervisión humana para operaciones sensibles.
            if (
                approval_required
                and self.supervision_mode
            ):
                print(
                    "\nAprobación requerida"
                )
                print(
                    f"Subagente: {subagent}"
                )
                print(
                    f"Tool: {tool_name}"
                )
                print(
                    f"Argumentos: {arguments}"
                )
                print(
                    "Motivo: "
                    f"{decision.approval_reason}"
                )

                approval = input(
                    "¿Aprobar? (yes/no): "
                ).strip().lower()

                approved_by_user = (
                    approval in {
                        "yes",
                        "y",
                        "si",
                        "sí",
                    }
                )

                if not approved_by_user:
                    task_state.record_tool_call(
                        subagent=subagent,
                        tool_name=tool_name,
                        args=arguments,
                        outcome=(
                            "denied_by_user"
                        ),
                    )

                    message = (
                        f"Ejecución de "
                        f"'{tool_name}' rechazada "
                        "por el usuario."
                    )

                    return finish(
                        result=message,
                        outcome=(
                            "denied_by_user"
                        ),
                        level="WARNING",
                        status_message=message,
                    )

            elif approval_required:
                # La política requiere aprobación, pero la ejecución
                # se encuentra fuera del modo supervisado.
                approved_by_user = None

            started_at = (
                time.perf_counter()
            )

            try:
                if tool_name == "run_command":
                    result = tool.execute(
                        **decision.arguments,
                        cwd=(
                            task_state
                            .workspace_path
                        ),
                    )

                else:
                    result = tool.execute(
                        **decision.arguments
                    )

                duration_ms = (
                    time.perf_counter()
                    - started_at
                ) * 1000

                rounded_duration = round(
                    duration_ms,
                    2,
                )

                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome="executed",
                    duration_ms=(
                        rounded_duration
                    ),
                )

                if tool.category == "write":
                    self._record_written_file(
                        decision_arguments=(
                            decision.arguments
                        ),
                        task_state=task_state,
                    )

                elif tool_name == "run_command":
                    self._record_workspace_side_effects(
                        task_state
                    )

                return finish(
                    result=result,
                    outcome="executed",
                    duration_ms=(
                        rounded_duration
                    ),
                )

            except Exception as exc:
                duration_ms = (
                    time.perf_counter()
                    - started_at
                ) * 1000

                rounded_duration = round(
                    duration_ms,
                    2,
                )

                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome=(
                        "execution_error"
                    ),
                    duration_ms=(
                        rounded_duration
                    ),
                )

                message = (
                    f"Error ejecutando "
                    f"{tool_name}: {exc}"
                )

                task_state.record_observation(
                    message
                )

                return finish(
                    result=(
                        "TOOL_EXECUTION_ERROR: "
                        f"{exc}"
                    ),
                    outcome=(
                        "execution_error"
                    ),
                    duration_ms=(
                        rounded_duration
                    ),
                    level="ERROR",
                    status_message=message,
                )

    @staticmethod
    def _record_written_file(
        *,
        decision_arguments: dict,
        task_state: TaskState,
    ) -> None:
        """
        Registra un archivo escrito por write_file como path relativo
        al workspace.

        La validación de política ya debería garantizar que el path se
        encuentre dentro del workspace. De todos modos, se maneja una
        posible inconsistencia sin ocultar el resultado de la tool.
        """

        path_value = (
            decision_arguments.get(
                "path"
            )
        )

        if not isinstance(
            path_value,
            (
                str,
                Path,
            ),
        ):
            task_state.record_observation(
                "La tool de escritura no "
                "informó un path válido."
            )

            return

        try:
            written_path = Path(
                path_value
            ).resolve()

            workspace = Path(
                task_state.workspace_path
            ).resolve()

            relative_path = (
                written_path.relative_to(
                    workspace
                )
            )

            task_state.record_file_modified(
                relative_path.as_posix()
            )

        except (
            OSError,
            ValueError,
        ) as exc:
            task_state.record_observation(
                "No se pudo normalizar el "
                "archivo escrito respecto del "
                f"workspace: {exc}"
            )

    # Directorios de salida generada. Si un comando los modifica,
    # no cuentan como cambios de código realizados por el agente.
    _GENERATED_DIR_NAMES = frozenset({
        "dist",
        "build",
        ".next",
        "out",
        "coverage",
    })

    @classmethod
    def _record_workspace_side_effects(
        cls,
        task_state: TaskState,
    ) -> None:
        """
        Después de un comando, inspecciona git status para detectar
        cambios reales producidos dentro del workspace.
        """

        workspace = (
            task_state.workspace_path
        )

        try:
            status = subprocess.run(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    ".",
                ],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if status.returncode != 0:
                return

            prefix_result = subprocess.run(
                [
                    "git",
                    "rev-parse",
                    "--show-prefix",
                ],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if (
                prefix_result.returncode
                != 0
            ):
                return

        except (
            OSError,
            subprocess.SubprocessError,
        ):
            return

        # git status devuelve paths relativos a la raíz del
        # repositorio. Se elimina el prefijo del workspace.
        prefix = (
            prefix_result.stdout.strip()
        )

        for line in (
            status.stdout.splitlines()
        ):
            if len(line) < 4:
                continue

            repo_relative_path = (
                line[3:].strip()
            )

            # Maneja archivos renombrados:
            # "archivo-viejo -> archivo-nuevo".
            if (
                " -> "
                in repo_relative_path
            ):
                repo_relative_path = (
                    repo_relative_path.split(
                        " -> ",
                        1,
                    )[1]
                )

            if (
                prefix
                and not repo_relative_path
                .startswith(prefix)
            ):
                continue

            workspace_relative_path = (
                repo_relative_path[
                    len(prefix):
                ]
            )

            if not workspace_relative_path:
                continue

            path_segments = (
                workspace_relative_path
                .split("/")
            )

            if (
                cls._GENERATED_DIR_NAMES
                .intersection(
                    path_segments
                )
            ):
                continue

            task_state.record_file_modified(
                workspace_relative_path
            )