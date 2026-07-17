import project_memory
from orchestrator import Orchestrator
from policy_engine import PolicyViolation
from task_state import SubagentResult


class FakeExplorer:
    def run(self, task_state):
        return SubagentResult(
            subagent="explorer",
            summary="ok",
            data={"archivos_relevantes": ["a.ts"]},
            sources=["repository"],
        )


class FakeResearcher:
    def run(self, task_state):
        return SubagentResult(
            subagent="researcher", summary="ok", data={}, sources=["rag"]
        )


class FakeReviewer:
    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1
        return SubagentResult(
            subagent="reviewer",
            summary="ok",
            data={"approved": True},
            sources=["repository"],
        )


class FakePolicyEngine:
    """Simula el chequeo de workspace de PolicyEngine sin leer un YAML."""

    def __init__(self, allowed_workspace):
        self.allowed_workspace = allowed_workspace

    def validate_workspace(self, workspace_path):
        if workspace_path != self.allowed_workspace:
            raise PolicyViolation(
                f"'{workspace_path}' no coincide con "
                f"'{self.allowed_workspace}'."
            )


class FakeImplementer:
    def __init__(self):
        self.calls = 0
        self.seen_tester_results = []

    def run(self, task_state):
        self.calls += 1
        tester_result = task_state.last_result_of("tester")
        self.seen_tester_results.append(
            tester_result.data if tester_result else None
        )
        return SubagentResult(
            subagent="implementer",
            summary=f"intento {self.calls}",
            data={"evidence_sufficient": True, "changes": []},
            sources=["repository"],
        )


class FakeImplementerDeclines:
    """Se niega a actuar: evidence_sufficient=False y no escribe nada."""

    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1
        return SubagentResult(
            subagent="implementer",
            summary=(
                "No se aplicaron cambios: restricción imposible de "
                "cumplir."
            ),
            data={
                "evidence_sufficient": False,
                "changes": [],
                "risks_or_notes": [
                    "El pedido contradice una restricción explícita."
                ],
            },
            sources=["repository"],
        )


class FakeTesterAlwaysPasses:
    """No hay nada que romper porque el Implementer no tocó nada."""

    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1
        return SubagentResult(
            subagent="tester",
            summary="ok",
            data={
                "all_passed": True,
                "checks": [],
                "validated_commands": {},
            },
            sources=["repository"],
        )


def _check(command, ok, stderr):
    return {
        "command": command,
        "ok": ok,
        "stderr": stderr,
        "return_code": 0 if ok else 1,
    }


class FakeTesterDifferentErrorsThenPasses:
    """Falla en 1 y 2 con errores DISTINTOS (progreso real), pasa en el 3."""

    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1

        if self.calls == 1:
            checks = [
                _check("npm test", False, "TypeError: cannot read foo")
            ]
        elif self.calls == 2:
            checks = [
                _check(
                    "npm test",
                    False,
                    "ReferenceError: bar is not defined",
                )
            ]
        else:
            checks = [_check("npm test", True, "")]

        passed = self.calls >= 3

        return SubagentResult(
            subagent="tester",
            summary="ok" if passed else "fail",
            data={"all_passed": passed, "checks": checks},
            sources=["repository"],
        )


class FakeTesterSameErrorTwice:
    """Falla dos veces seguidas con EXACTAMENTE el mismo error."""

    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1

        checks = [
            _check(
                "npm run build",
                False,
                "TS2339: Property 'priority' does not exist",
            )
        ]

        return SubagentResult(
            subagent="tester",
            summary="fail",
            data={"all_passed": False, "checks": checks},
            sources=["repository"],
        )


class FakeTesterAlwaysDifferentErrors:
    """
    Nunca pasa, pero cada intento tiene un error de tipo distinto -- no
    es un loop, es simplemente insuficiente.
    """

    ERRORS = [
        "TypeError: cannot read property of undefined",
        "ReferenceError: identifier is not defined",
        "SyntaxError: unexpected token in expression",
    ]

    def __init__(self):
        self.calls = 0

    def run(self, task_state):
        self.calls += 1

        checks = [
            _check("npm test", False, self.ERRORS[self.calls - 1])
        ]

        return SubagentResult(
            subagent="tester",
            summary="fail",
            data={"all_passed": False, "checks": checks},
            sources=["repository"],
        )


def build_orchestrator(implementer, tester, reviewer):
    orch = Orchestrator()
    orch.register("explorer", FakeExplorer())
    orch.register("researcher", FakeResearcher())
    orch.register("implementer", implementer)
    orch.register("tester", tester)
    orch.register("reviewer", reviewer)
    return orch


def test_recovers_with_different_errors_then_passes():
    implementer = FakeImplementer()
    tester = FakeTesterDifferentErrorsThenPasses()
    reviewer = FakeReviewer()

    orch = build_orchestrator(implementer, tester, reviewer)
    result = orch.run("pedido de prueba", workspace_path=".")

    assert implementer.calls == 3
    assert tester.calls == 3
    assert reviewer.calls == 1
    assert result.status == "done"


def test_stops_when_same_error_repeats():
    implementer = FakeImplementer()
    tester = FakeTesterSameErrorTwice()
    reviewer = FakeReviewer()

    orch = build_orchestrator(implementer, tester, reviewer)
    result = orch.run("pedido de prueba", workspace_path=".")

    # Se corta apenas se detecta el segundo fallo idéntico.
    # No agota los 3 intentos ni ejecuta el Reviewer.
    assert implementer.calls == 2
    assert tester.calls == 2
    assert reviewer.calls == 0

    assert result.status == "needs_help"

    assert any(
        "Loop detectado" in line
        for line in result.progress_log
    )

    assert any(
        "Loop de reintentos" in observation
        for observation in result.observations
    )


def test_gives_up_after_max_distinct_failures():
    implementer = FakeImplementer()
    tester = FakeTesterAlwaysDifferentErrors()
    reviewer = FakeReviewer()

    orch = build_orchestrator(implementer, tester, reviewer)
    result = orch.run("pedido de prueba", workspace_path=".")

    # Nunca se repite el mismo error, así que agota los 3 intentos.
    assert implementer.calls == 3
    assert tester.calls == 3
    assert reviewer.calls == 1
    assert result.status == "blocked"
    assert "las validaciones fallaron" in result.progress_log[-1]


def test_needs_help_when_implementer_declines():
    implementer = FakeImplementerDeclines()
    tester = FakeTesterAlwaysPasses()
    reviewer = FakeReviewer()

    orch = build_orchestrator(implementer, tester, reviewer)
    result = orch.run("pedido de prueba", workspace_path=".")

    # No hace falta reintentar -- el Tester "pasa" trivial en el
    # primer intento porque no hay nada que romper.
    assert implementer.calls == 1
    assert tester.calls == 0
    assert reviewer.calls == 0
    assert result.status == "needs_help"
    assert any(
        "declinó actuar" in obs for obs in result.observations
    )


def test_fails_fast_on_workspace_mismatch():
    """
    Si el workspace no coincide con el de agent.config.yaml, no debería
    llamarse a NINGÚN subagente -- antes este caso corría el pipeline
    entero (varias llamadas reales al LLM) para terminar bloqueado de
    todos modos.
    """

    implementer = FakeImplementer()
    tester = FakeTesterAlwaysPasses()
    reviewer = FakeReviewer()
    explorer = FakeExplorer()
    researcher = FakeResearcher()

    orch = Orchestrator(
        policy_engine=FakePolicyEngine(
            allowed_workspace="/algun/otro/workspace"
        )
    )
    orch.register("explorer", explorer)
    orch.register("researcher", researcher)
    orch.register("implementer", implementer)
    orch.register("tester", tester)
    orch.register("reviewer", reviewer)

    result = orch.run("pedido de prueba", workspace_path=".")

    assert implementer.calls == 0
    assert tester.calls == 0
    assert reviewer.calls == 0
    assert result.status == "blocked"
    assert any(
        "no autorizado" in line for line in result.progress_log
    )


def test_run_survives_memory_save_failure(monkeypatch):
    """
    Un fallo al guardar la memoria del proyecto (ej. permisos) no debe
    tirar abajo toda la corrida ni ocultar el resultado real de la
    tarea.
    """

    def _broken_save(self):
        raise OSError("disco lleno (simulado)")

    monkeypatch.setattr(
        project_memory.ProjectMemory, "save", _broken_save
    )

    implementer = FakeImplementer()
    tester = FakeTesterDifferentErrorsThenPasses()
    reviewer = FakeReviewer()

    orch = build_orchestrator(implementer, tester, reviewer)

    # No debe levantar excepción.
    result = orch.run("pedido de prueba", workspace_path=".")

    assert result.status == "done"
    assert any(
        "No se pudo guardar la memoria" in line
        for line in result.progress_log
    )
