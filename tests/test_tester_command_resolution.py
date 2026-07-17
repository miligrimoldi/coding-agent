from subagents.tester import Tester
from task_state import TaskState, SubagentResult

# Evita que pytest intente coleccionar Tester como clase de test solo
# porque su nombre empieza con "Test".
Tester.__test__ = False


class FakeMemory:
    def __init__(self, useful_commands):
        self.data = {"useful_commands": useful_commands}


def make_task_state(scripts_detectados, useful_commands):
    task_state = TaskState(original_request="x", workspace_path=".")
    task_state.record_subagent_result(SubagentResult(
        subagent="explorer",
        summary="ok",
        data={"scripts_detectados": scripts_detectados},
        sources=["repository"],
    ))
    task_state.project_memory = FakeMemory(useful_commands)
    return task_state


def test_lint_not_dropped_when_only_other_keys_in_memory():
    """
    Reproduce el bug real: lint nunca pasó (no está en memoria), pero
    build/test/prisma_validate sí. lint tiene que seguir apareciendo.
    """

    task_state = make_task_state(
        scripts_detectados={
            "lint": "eslint --fix",
            "build": "nest build",
            "test": "jest",
        },
        useful_commands={
            "prisma_validate": "npx prisma validate",
            "build": "npm run build",
            "test": "npm run test",
        },
    )

    tester = Tester(tool_executor=None)
    commands, source = tester._resolve_commands(task_state)

    keys = [key for key, _ in commands]
    command_by_key = dict(commands)

    assert "lint" in keys
    assert source == "explorer+memory"
    # Las claves que sí están en memoria usan el comando ya validado, no
    # el que se reconstruiría a partir de scripts_detectados.
    assert command_by_key["build"] == "npm run build"
    assert command_by_key["test"] == "npm run test"
    assert command_by_key["lint"] == "npm run lint"  # viene del explorer


def test_memory_only_when_explorer_empty():
    task_state = make_task_state(
        scripts_detectados={"lint": "", "build": "", "test": ""},
        useful_commands={
            "build": "npm run build",
            "test": "npm run test",
        },
    )

    tester = Tester(tool_executor=None)
    commands, source = tester._resolve_commands(task_state)

    assert source == "memory"
    assert dict(commands) == {
        "build": "npm run build",
        "test": "npm run test",
    }


def test_falls_back_to_default_when_nothing_available():
    task_state = make_task_state(
        scripts_detectados={"lint": "", "build": "", "test": ""},
        useful_commands={},
    )

    tester = Tester(tool_executor=None)
    commands, source = tester._resolve_commands(task_state)

    assert source == "default"
    assert commands == Tester.DEFAULT_TEST_COMMANDS
