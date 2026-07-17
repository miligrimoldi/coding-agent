import json
from typing import Optional

from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor


class Tester:
    ALLOWED_TOOLS = ["run_command"]

    # Comandos a probar cuando no hay override manual, ni memoria del
    # proyecto, ni scripts_detectados del Explorer.
    DEFAULT_TEST_COMMANDS = [
        ("prisma_validate", "npx prisma validate"),
        ("build", "npm run build"),
        ("test", "npm test -- --runInBand"),
    ]

    # Orden en el que se corren los scripts de package.json que el
    # Explorer haya detectado, y en el que se buscan en la memoria del
    # proyecto (que guarda comandos ya validados en corridas anteriores).
    COMMAND_KEYS = ["prisma_validate", "lint", "build", "test"]

    def __init__(
        self,
        tool_executor: ToolExecutor,
        test_commands: Optional[list[str]] = None,
    ):
        self.tool_executor = tool_executor
        self.override_test_commands = test_commands

    def run(self, task_state: TaskState) -> SubagentResult:
        task_state.set_phase("testing")

        labeled_commands, commands_source = self._resolve_commands(
            task_state
        )

        checks = []
        validated_commands: dict[str, str] = {}

        for key, command in labeled_commands:
            output = self.tool_executor.execute(
                subagent="tester",
                tool_name="run_command",
                arguments={"command": command},
                task_state=task_state,
                allowed_tools=self.ALLOWED_TOOLS,
            )

            result = self._parse_result(command, output)
            checks.append(result)

            if result["ok"]:
                validated_commands[key] = command
            else:
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
                "commands_source": commands_source,
                "validated_commands": validated_commands,
            },
            sources=["repository"],
        )

    def _resolve_commands(
        self,
        task_state: TaskState,
    ) -> tuple[list[tuple[str, str]], str]:

        if self.override_test_commands:
            return (
                [
                    (f"override_{index}", command)
                    for index, command in enumerate(
                        self.override_test_commands
                    )
                ],
                "override",
            )

        explorer_commands = dict(self._commands_from_explorer(task_state))
        memory_commands = dict(self._commands_from_memory(task_state))

        merged = {**explorer_commands, **memory_commands}

        if not merged:
            return self.DEFAULT_TEST_COMMANDS, "default"

        if explorer_commands and memory_commands:
            source = "explorer+memory"
        elif memory_commands:
            source = "memory"
        else:
            source = "explorer"

        ordered = [
            (key, merged[key])
            for key in self.COMMAND_KEYS
            if key in merged
        ]

        return ordered, source

    @staticmethod
    def _commands_from_memory(
        task_state: TaskState,
    ) -> list[tuple[str, str]]:
        memory = task_state.project_memory

        if memory is None:
            return []

        useful_commands = memory.data.get("useful_commands")

        if not isinstance(useful_commands, dict) or not useful_commands:
            return []

        return [
            (key, useful_commands[key])
            for key in Tester.COMMAND_KEYS
            if useful_commands.get(key)
        ]

    @staticmethod
    def _commands_from_explorer(
        task_state: TaskState,
    ) -> list[tuple[str, str]]:
        explorer_result = task_state.last_result_of("explorer")
        explorer_data = explorer_result.data if explorer_result else {}

        scripts_detectados = explorer_data.get("scripts_detectados")

        if not isinstance(scripts_detectados, dict):
            return []

        commands = [
            (key, f"npm run {key}")
            for key in ("lint", "build", "test")
            if scripts_detectados.get(key)
        ]

        if commands and Tester._uses_prisma(explorer_data):
            commands.insert(0, ("prisma_validate", "npx prisma validate"))

        return commands

    @staticmethod
    def _uses_prisma(explorer_data: dict) -> bool:
        dependencies = [
            str(dependency).lower()
            for dependency in explorer_data.get(
                "dependencias_detectadas", []
            )
        ]

        relevant_files = [
            str(path).lower()
            for path in explorer_data.get("archivos_relevantes", [])
        ]

        return (
            any("prisma" in dependency for dependency in dependencies)
            or any("schema.prisma" in path for path in relevant_files)
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