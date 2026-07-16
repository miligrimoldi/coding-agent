# interfaz para los subagentes
from typing import Protocol

from task_state import TaskState, SubagentResult


class Subagent(Protocol):
    def run(self, task_state: TaskState) -> SubagentResult:
        ...