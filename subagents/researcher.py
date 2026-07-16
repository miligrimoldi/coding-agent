from task_state import TaskState, SubagentResult


class Researcher:
    def run(self, task_state: TaskState) -> SubagentResult:
        raise NotImplementedError(
            "Researcher: pendiente de implementar (RAG + fallback a web_search)."
        )