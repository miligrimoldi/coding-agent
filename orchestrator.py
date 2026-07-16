# agente principal
import os
from typing import Optional

from task_state import TaskState, SubagentResult
from subagents.subagent_protocol import Subagent


class SubagentError(Exception):
    pass


class Orchestrator:
    def __init__(self):
        self.subagents: dict = {}   # nombre -> SubagentFn

    def register(self, name: str, subagent: Subagent) -> None:
        self.subagents[name] = subagent

    def call_subagent(self, name: str, task_state: TaskState) -> SubagentResult:
        if name not in self.subagents:
            raise SubagentError(f"Subagente '{name}' no esta registrado.")

        task_state.log(f"Llamando a subagente: {name}")
        try:
            result = self.subagents[name].run(task_state)
        except Exception as e:
            task_state.record_observation(f"Fallo el subagente {name}: {e}")
            raise SubagentError(f"El subagente {name} fallo: {e}") from e

        task_state.record_subagent_result(result)
        return result

    def run(self, user_request: str, workspace_path: Optional[str] = None) -> TaskState:
        """
        Secuencia fija para el caso de uso "agregar una funcionalidad al
        repositorio": Explorer -> Researcher -> Implementer (modifica
        codigo real) -> Tester (corre tests/build/lint reales) ->
        Reviewer (revisa el diff contra el pedido original).
        """
        task_state = TaskState(original_request=user_request)
        sequence = ["explorer", "researcher", "implementer", "tester", "reviewer"]

        original_cwd = os.getcwd()
        try:
            if workspace_path:
                abs_workspace = os.path.abspath(workspace_path)
                os.chdir(workspace_path)
                task_state.log(f"Workspace: {abs_workspace}")

            for step in sequence:
                try:
                    self.call_subagent(step, task_state)
                except SubagentError as e:
                    task_state.status = "blocked"
                    task_state.log(f"Tarea bloqueada en el paso '{step}': {e}")
                    return task_state

            task_state.status = "done"
            task_state.log("Tarea completada.")
            return task_state
        finally:
            os.chdir(original_cwd)