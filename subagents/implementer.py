from task_state import TaskState, SubagentResult


class Implementer:
    def run(self, task_state: TaskState) -> SubagentResult:
        raise NotImplementedError(
            "Implementer: pendiente de implementar (modificacion real de codigo)."
        )