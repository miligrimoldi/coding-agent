from task_state import TaskState, SubagentResult


class Reviewer:
    def run(self, task_state: TaskState) -> SubagentResult:
        raise NotImplementedError(
            "Reviewer: pendiente de implementar (revision del diff contra el pedido)."
        )