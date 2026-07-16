import json
from typing import Optional

from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor


DEFAULT_TEST_COMMANDS = [
    "npx prisma validate",
    "npm run build",
    "npm test -- --runInBand",
]


class Tester:
    ALLOWED_TOOLS = ["run_command"]

    def __init__(
        self,
        tool_executor: ToolExecutor,
        test_commands: Optional[list[str]] = None,
    ):
        self.tool_executor = tool_executor
        self.test_commands = test_commands or DEFAULT_TEST_COMMANDS

    def run(self, task_state: TaskState) -> SubagentResult:
        task_state.set_phase("testing")

        checks = []

        for command in self.test_commands:
            output = self.tool_executor.execute(
                subagent="tester",
                tool_name="run_command",
                arguments={"command": command},
                task_state=task_state,
                allowed_tools=self.ALLOWED_TOOLS,
            )

            result = self._parse_result(command, output)
            checks.append(result)

            if not result["ok"]:
                task_state.record_observation(
                    f"Tester: falló '{command}'. "
                    f"Error: {result['stderr']}"
                )

        all_passed = all(check["ok"] for check in checks)

        return SubagentResult(
            subagent="tester",
            summary=(
                "Todas las validaciones pasaron."
                if all_passed
                else "Una o más validaciones fallaron."
            ),
            data={
                "all_passed": all_passed,
                "checks": checks,
            },
            sources=["repository"],
        )

    @staticmethod
    def _parse_result(command: str, output: str) -> dict:
        try:
            parsed = json.loads(output)

            return {
                "command": command,
                "ok": bool(parsed.get("ok")),
                "stdout": parsed.get("stdout", ""),
                "stderr": parsed.get("stderr", ""),
                "return_code": parsed.get("return_code"),
                "timed_out": parsed.get("timed_out", False),
            }

        except json.JSONDecodeError:
            return {
                "command": command,
                "ok": False,
                "stdout": "",
                "stderr": output,
                "return_code": None,
                "timed_out": False,
            }