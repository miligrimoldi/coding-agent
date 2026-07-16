
# Uso: python3 main.py /ruta/al/repo "pedido en lenguaje natural"

import sys

from orchestrator import Orchestrator
from subagents.explorer import Explorer
from subagents.researcher import Researcher
from subagents.implementer import Implementer
from subagents.tester import Tester
from subagents.reviewer import Reviewer


def build_orchestrator() -> Orchestrator:
    orch = Orchestrator()
    orch.register("explorer", Explorer())
    orch.register("researcher", Researcher())
    orch.register("implementer", Implementer())
    orch.register("tester", Tester())
    orch.register("reviewer", Reviewer())
    return orch


if __name__ == "__main__":
    workspace = sys.argv[1] if len(sys.argv) > 1 else "."
    user_request = (
        sys.argv[2] if len(sys.argv) > 2
        else "Agregar una funcionalidad al proyecto y validar que los tests pasen."
    )

    orchestrator = build_orchestrator()
    final_state = orchestrator.run(user_request, workspace_path=workspace)

    print(final_state.to_json())