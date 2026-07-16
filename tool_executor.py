import time
from pathlib import Path
from typing import Collection, Optional

from policy_engine import PolicyEngine, PolicyViolation
from task_state import TaskState
from tools.loader import get_tool


class ToolExecutor:
    def __init__(
        self,
        policy_engine: PolicyEngine,
        supervision_mode: bool = True,
    ):
        self.policy_engine = policy_engine
        self.supervision_mode = supervision_mode

    def execute(
        self,
        *,
        subagent: str,
        tool_name: str,
        arguments: dict,
        task_state: TaskState,
        allowed_tools: Optional[Collection[str]] = None,
    ) -> str:
        if allowed_tools is not None and tool_name not in allowed_tools:
            message = (
                f"El subagente '{subagent}' no tiene permitido usar "
                f"la tool '{tool_name}'."
            )

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="blocked_by_agent_permissions",
            )
            task_state.record_observation(message)
            return f"POLICY_BLOCKED: {message}"

        try:
            tool = get_tool(tool_name)

            decision = self.policy_engine.validate(
                tool=tool,
                arguments=arguments,
                workspace_path=task_state.workspace_path,
            )

        except (ValueError, PolicyViolation) as exc:
            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="blocked_by_policy",
            )
            task_state.record_observation(str(exc))
            return f"POLICY_BLOCKED: {exc}"

        if decision.requires_approval and self.supervision_mode:
            print("\nAprobación requerida")
            print(f"Subagente: {subagent}")
            print(f"Tool: {tool_name}")
            print(f"Argumentos: {arguments}")
            print(f"Motivo: {decision.approval_reason}")

            approval = input("¿Aprobar? (yes/no): ").strip().lower()

            if approval not in {"yes", "y", "si", "sí"}:
                task_state.record_tool_call(
                    subagent=subagent,
                    tool_name=tool_name,
                    args=arguments,
                    outcome="denied_by_user",
                )

                return (
                    f"Ejecución de '{tool_name}' rechazada por el usuario."
                )

        started_at = time.perf_counter()

        try:
            if tool_name == "run_command":
                result = tool.execute(
                    **decision.arguments,
                    cwd=task_state.workspace_path,
                )
            else:
                result = tool.execute(**decision.arguments)

            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="executed",
                duration_ms=round(duration_ms, 2),
            )

            if tool.category == "write":
                written_path = Path(decision.arguments["path"])
                relative_path = written_path.relative_to(
                    Path(task_state.workspace_path)
                )
                task_state.record_file_modified(
                    relative_path.as_posix()
                )

            return result

        except Exception as exc:
            duration_ms = (
                time.perf_counter() - started_at
            ) * 1000

            task_state.record_tool_call(
                subagent=subagent,
                tool_name=tool_name,
                args=arguments,
                outcome="execution_error",
                duration_ms=round(duration_ms, 2),
            )

            task_state.record_observation(
                f"Error ejecutando {tool_name}: {exc}"
            )

            return f"TOOL_EXECUTION_ERROR: {exc}"