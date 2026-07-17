import subprocess
import time
from pathlib import Path
from typing import Collection, Optional

from policy_engine import PolicyEngine, PolicyViolation
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
        allowed_tools: Optional[Collection[str]] = None,
    ) -> str:
        # Copia los argumentos para normalizarlos sin modificar
        # el diccionario original enviado por el subagente.
        arguments = dict(arguments or {})

        # Para list_files, un path vacío representa la raíz del
        # workspace. Se normaliza antes de validar la política.
        if tool_name == "list_files":
            path_argument = arguments.get("path")

            if (
                not isinstance(path_argument, str)
                or not path_argument.strip()
            ):
                arguments["path"] = "."

        if allowed_tools is not None and tool_name not in allowed_tools:
            message = (
                f"El subagente '{subagent}' no tiene permitido usar "
                f"la tool '{tool_name}'."
            )

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="blocked_by_agent_permissions",
            )

            task_state.record_observation(message)

            return f"POLICY_BLOCKED: {message}"

        try:
            tool = get_tool(tool_name)

            decision = self.policy_engine.validate(
                tool=tool,
                arguments=arguments,
                workspace_path=task_state.workspace_path,
            )

        except (ValueError, PolicyViolation) as exc:
            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="blocked_by_policy",
            )

            task_state.record_observation(str(exc))

            return f"POLICY_BLOCKED: {exc}"

        if decision.requires_approval and self.supervision_mode:
            print("\nAprobación requerida")
            print(f"Subagente: {subagent}")
            print(f"Tool: {tool_name}")
            print(f"Argumentos: {arguments}")
            print(f"Motivo: {decision.approval_reason}")

            approval = input(
                "¿Aprobar? (yes/no): "
            ).strip().lower()

            if approval not in {
                "yes",
                "y",
                "si",
                "sí",
            }:
                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome="denied_by_user",
                )

                return (
                    f"Ejecución de '{tool_name}' "
                    "rechazada por el usuario."
                )

        started_at = time.perf_counter()

        try:
            if tool_name == "run_command":
                result = tool.execute(
                    **decision.arguments,
                    cwd=task_state.workspace_path,
                )
            else:
                result = tool.execute(
                    **decision.arguments
                )

            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="executed",
                duration_ms=round(
                    duration_ms,
                    2,
                ),
            )

            if tool.category == "write":
                written_path = Path(
                    decision.arguments["path"]
                )

                relative_path = written_path.relative_to(
                    Path(task_state.workspace_path)
                )

                task_state.record_file_modified(
                    relative_path.as_posix()
                )

            elif tool_name == "run_command":
                self._record_workspace_side_effects(
                    task_state
                )

            return result

        except Exception as exc:
            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="execution_error",
                duration_ms=round(
                    duration_ms,
                    2,
                ),
            )

            task_state.record_observation(
                f"Error ejecutando {tool_name}: {exc}"
            )

            return f"TOOL_EXECUTION_ERROR: {exc}"

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
        workspace = task_state.workspace_path

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

            if prefix_result.returncode != 0:
                return

        except (OSError, subprocess.SubprocessError):
            return

        # git status devuelve paths relativos a la raíz del
        # repositorio. Se elimina el prefijo del workspace.
        prefix = prefix_result.stdout.strip()

        for line in status.stdout.splitlines():
            repo_relative_path = line[3:].strip()

            # Maneja archivos renombrados:
            # "archivo-viejo -> archivo-nuevo".
            if " -> " in repo_relative_path:
                repo_relative_path = repo_relative_path.split(
                    " -> ",
                    1,
                )[1]

            if (
                prefix
                and not repo_relative_path.startswith(prefix)
            ):
                continue

            workspace_relative_path = (
                repo_relative_path[len(prefix):]
            )

            if not workspace_relative_path:
                continue

            path_segments = (
                workspace_relative_path.split("/")
            )

            if cls._GENERATED_DIR_NAMES.intersection(
                path_segments
            ):
                continue

            task_state.record_file_modified(
                workspace_relative_path
            )