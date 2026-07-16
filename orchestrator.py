from pathlib import Path
from typing import Optional

from task_state import TaskState, SubagentResult
from subagents.subagent_protocol import Subagent


class SubagentError(Exception):
    pass


class Orchestrator:
    def __init__(self):
        self.subagents: dict[str, Subagent] = {}

    def register(
        self,
        name: str,
        subagent: Subagent,
    ) -> None:
        self.subagents[name] = subagent

    def call_subagent(
        self,
        name: str,
        task_state: TaskState,
    ) -> SubagentResult:
        if name not in self.subagents:
            raise SubagentError(
                f"Subagente '{name}' no está registrado."
            )

        task_state.log(f"Llamando a subagente: {name}")

        try:
            result = self.subagents[name].run(task_state)
        except Exception as exc:
            task_state.record_observation(
                f"Falló el subagente {name}: {exc}"
            )

            raise SubagentError(
                f"El subagente {name} falló: {exc}"
            ) from exc

        task_state.record_subagent_result(result)
        return result

    def run(
        self,
        user_request: str,
        workspace_path: Optional[str] = None,
    ) -> TaskState:
        workspace = Path(workspace_path or ".").resolve()

        if not workspace.exists():
            raise FileNotFoundError(
                f"El workspace no existe: {workspace}"
            )

        if not workspace.is_dir():
            raise NotADirectoryError(
                f"El workspace no es una carpeta: {workspace}"
            )

        task_state = TaskState(
            original_request=user_request,
            workspace_path=str(workspace),
        )

        task_state.log(f"Workspace: {workspace}")

        sequence = [
            "explorer",
            "researcher",
            "implementer",
            "tester",
            "reviewer",
        ]

        for step in sequence:
            try:
                self.call_subagent(step, task_state)
            except SubagentError as exc:
                task_state.status = "blocked"
                task_state.log(
                    f"Tarea bloqueada en el paso '{step}': {exc}"
                )
                return task_state

        tester_result = task_state.last_result_of("tester")

        if (
            tester_result
            and not tester_result.data.get("all_passed", False)
        ):
            task_state.status = "blocked"
            task_state.log(
                "La ejecución terminó, pero las validaciones fallaron."
            )
        else:
            task_state.status = "done"
            task_state.log("Tarea completada.")

        return task_state