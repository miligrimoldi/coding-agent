import sys

from orchestrator import Orchestrator
from policy_engine import PolicyEngine
from tool_executor import ToolExecutor

from subagents.explorer import Explorer
from subagents.researcher import Researcher
from subagents.implementer import Implementer
from subagents.tester import Tester
from subagents.reviewer import Reviewer


def build_orchestrator() -> Orchestrator:
    policy_engine = PolicyEngine.from_file(
        "agent.config.yaml"
    )

    tool_executor = ToolExecutor(
        policy_engine=policy_engine,
        supervision_mode=True,
    )

    orchestrator = Orchestrator(policy_engine=policy_engine)

    orchestrator.register(
        "explorer",
        Explorer(tool_executor),
    )

    orchestrator.register(
        "researcher",
        Researcher(tool_executor),
    )

    orchestrator.register(
        "implementer",
        Implementer(tool_executor),
    )

    orchestrator.register(
        "tester",
        Tester(tool_executor),
    )

    orchestrator.register(
        "reviewer",
        Reviewer(tool_executor),
    )

    return orchestrator


if __name__ == "__main__":
    workspace = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "./target-project/issue-tracker-api"
    )

    user_request = (
        sys.argv[2]
        if len(sys.argv) > 2
        else (
            "Agregar una funcionalidad al proyecto "
            "y validar que los tests pasen."
        )
    )

    orchestrator = build_orchestrator()

    final_state = orchestrator.run(
        user_request=user_request,
        workspace_path=workspace,
    )

    print(final_state.to_json())