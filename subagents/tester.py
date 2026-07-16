from task_state import TaskState, SubagentResult
from tools.loader import get_implementations_for

DEFAULT_TEST_COMMAND = "pytest"


class Tester:
    def __init__(self, test_command: str = DEFAULT_TEST_COMMAND):
        self.test_command = test_command
        # El Tester solo tiene permitido usar run_command -- ninguna
        # otra tool le hace falta para su trabajo.
        self._run_command = get_implementations_for(["run_command"])["run_command"]

    def run(self, task_state: TaskState) -> SubagentResult:
        task_state.record_tool_call("run_command", {"command": self.test_command})
        output = self._run_command(command=self.test_command)

        passed = self._interpret(output)

        if not passed:
            task_state.record_observation(
                f"Tester: el comando '{self.test_command}' fallo.\n{output}"
            )

        return SubagentResult(
            subagent="tester",
            summary=(
                f"Comando '{self.test_command}' "
                f"{'paso correctamente' if passed else 'fallo'}."
            ),
            data={
                "ok": passed,
                "command": self.test_command,
                "output": output,
            },
            sources=["repo"],
        )

    @staticmethod
    def _interpret(output: str) -> bool:
        return "RETURN_CODE: 0" in output