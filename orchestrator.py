import hashlib
import re
from pathlib import Path
from typing import Optional

from policy_engine import PolicyEngine, PolicyViolation
from project_memory import ProjectMemory
from task_state import TaskState, SubagentResult
from subagents.subagent_protocol import Subagent


_DIGITS_PATTERN = re.compile(r"\d+")


class SubagentError(Exception):
    pass


class Orchestrator:
    # Intentos totales del ciclo implementer -> tester (1 intento inicial +
    # reintentos). Si el Tester sigue fallando después de esto, se sigue
    # igual hacia el Reviewer, pero el resultado final queda "blocked".
    MAX_IMPLEMENT_ATTEMPTS = 3

    def __init__(self, policy_engine: Optional[PolicyEngine] = None):
        self.subagents: dict[str, Subagent] = {}
        # Opcional a propósito: los tests unitarios instancian el
        # Orchestrator con subagentes falsos y sin PolicyEngine.
        self.policy_engine = policy_engine

    def register(
        self,
        name: str,
        subagent: Subagent,
    ) -> None:
        self.subagents[name] = subagent

    def call_subagent(
        self,
        name: str,
        task_state: TaskState,
    ) -> SubagentResult:
        if name not in self.subagents:
            raise SubagentError(
                f"Subagente '{name}' no está registrado."
            )

        task_state.log(f"Llamando a subagente: {name}")

        try:
            result = self.subagents[name].run(task_state)
        except Exception as exc:
            task_state.record_observation(
                f"Falló el subagente {name}: {exc}"
            )

            raise SubagentError(
                f"El subagente {name} falló: {exc}"
            ) from exc

        task_state.record_subagent_result(result)
        return result

    def _try_call(
        self,
        task_state: TaskState,
        step: str,
    ) -> bool:
        """
        Llama a un subagente y, si falla, marca la tarea como bloqueada.
        Devuelve False cuando hay que cortar la ejecución.
        """

        try:
            self.call_subagent(step, task_state)
            return True
        except SubagentError as exc:
            task_state.status = "blocked"
            task_state.log(
                f"Tarea bloqueada en el paso '{step}': {exc}"
            )
            return False

    @staticmethod
    def _fingerprint_failures(failing_checks: list[dict]) -> Optional[str]:
        """
        Resume qué comandos fallaron y con qué tipo de error, ignorando
        ruido que cambia entre corridas aunque el problema de fondo sea
        el mismo (duraciones, timestamps, números de línea puntuales).
        """

        if not failing_checks:
            return None

        parts = []

        for check in sorted(failing_checks, key=lambda c: c["command"]):
            normalized_stderr = _DIGITS_PATTERN.sub(
                "#", check.get("stderr", "")
            )[:300]

            parts.append(
                f"{check['command']}|{check.get('return_code')}|"
                f"{normalized_stderr}"
            )

        digest = hashlib.sha256(
            "\n".join(parts).encode("utf-8")
        ).hexdigest()

        return digest

    def _run_implement_and_test_cycle(
        self,
        task_state: TaskState,
    ) -> bool:
        """
        Corre implementer -> tester, y si el Tester falla, vuelve a llamar
        al Implementer (que recibe el resultado del Tester como contexto
        para corregir) hasta MAX_IMPLEMENT_ATTEMPTS intentos en total.

        Si dos intentos consecutivos fallan con exactamente el mismo error
        (mismos comandos, mismo tipo de fallo), el Implementer no está
        progresando -- se corta el ciclo antes de agotar los intentos, se
        marca la tarea como "needs_help" y se deja registrado qué se
        intentó y en qué quedó trabado, en vez de seguir reintentando a
        ciegas.

        De paso alimenta la memoria del proyecto: comandos que efectivamente
        funcionaron, la decisión final si se logró resolver, y el bug si
        hubo que reintentar (resuelto, agotado, o abandonado por loop).

        Devuelve False solo si algún subagente revienta con una excepción
        (corta la ejecución). En cualquier otro desenlace devuelve True --
        se sigue hacia el Reviewer para que deje su propia constancia, y
        es _finalize_status quien decide el status final (salvo que ya
        haya quedado en "needs_help" por loop detectado).
        """

        memory = task_state.project_memory
        failed_commands_history: list[str] = []
        previous_fingerprint: Optional[str] = None

        for attempt in range(1, self.MAX_IMPLEMENT_ATTEMPTS + 1):
            if not self._try_call(task_state, "implementer"):
                return False

            if not self._try_call(task_state, "tester"):
                return False

            tester_result = task_state.last_result_of("tester")

            validated_commands = tester_result.data.get(
                "validated_commands", {}
            )

            if memory and validated_commands:
                memory.update_useful_commands(validated_commands)

            if tester_result.data.get("all_passed", False):
                implementer_result = task_state.last_result_of(
                    "implementer"
                )

                # El Tester "pasa" trivialmente si el Implementer no tocó
                # nada -- eso no es un éxito, es que declinó actuar por
                # falta de evidencia o por una restricción imposible de
                # cumplir. Hay que decirlo explícitamente en vez de dejar
                # que se cuele como si la tarea hubiera avanzado.
                implementer_declined = bool(
                    implementer_result
                    and implementer_result.data.get(
                        "evidence_sufficient"
                    ) is False
                    and not task_state.files_modified
                )

                if implementer_declined:
                    reasons = "; ".join(
                        implementer_result.data.get(
                            "risks_or_notes", []
                        )
                    ) or implementer_result.data.get("summary", "")

                    task_state.status = "needs_help"

                    task_state.log(
                        "El Implementer no encontró evidencia suficiente "
                        "para aplicar el pedido de forma segura y no "
                        "modificó ningún archivo; se pide ayuda en vez "
                        "de continuar."
                    )

                    task_state.record_observation(
                        f"Implementer declinó actuar: {reasons}"
                    )

                    if memory:
                        memory.record_bug(
                            description=(
                                "Pedido no resuelto por falta de "
                                f"evidencia o restricciones: {reasons}"
                            ),
                            resolved=False,
                            resolution="",
                        )

                    return True

                if memory and failed_commands_history:
                    memory.record_bug(
                        description="; ".join(
                            dict.fromkeys(failed_commands_history)
                        ),
                        resolved=True,
                        resolution=f"Resuelto en el intento {attempt}.",
                    )

                if memory:
                    memory.record_decision(
                        request=task_state.original_request,
                        summary=(
                            implementer_result.data.get("summary", "")
                            if implementer_result
                            else ""
                        ),
                        files=list(task_state.files_modified),
                    )

                return True

            failing_checks = [
                check
                for check in tester_result.data.get("checks", [])
                if not check.get("ok", False)
            ]

            failed_commands_history.extend(
                check["command"] for check in failing_checks
            )

            fingerprint = self._fingerprint_failures(failing_checks)

            if (
                fingerprint is not None
                and fingerprint == previous_fingerprint
            ):
                task_state.status = "needs_help"

                task_state.log(
                    "Loop detectado: el Tester volvió a fallar exactamente "
                    f"igual que en el intento anterior (intento {attempt}). "
                    "El Implementer no está progresando -- se corta el "
                    "ciclo en vez de seguir reintentando a ciegas."
                )

                failing_command_names = ", ".join(
                    dict.fromkeys(
                        check["command"] for check in failing_checks
                    )
                )

                task_state.record_observation(
                    "Loop de reintentos sin avance: los comandos "
                    f"'{failing_command_names}' siguen fallando con el "
                    "mismo error tras corregir. Hace falta intervención "
                    "humana para diagnosticar la causa de fondo."
                )

                if memory:
                    memory.record_bug(
                        description="; ".join(
                            dict.fromkeys(failed_commands_history)
                        ),
                        resolved=False,
                        resolution=(
                            "Loop detectado: mismo error repetido sin "
                            "cambios entre intentos; se pidió ayuda."
                        ),
                    )

                return True

            previous_fingerprint = fingerprint

            if attempt < self.MAX_IMPLEMENT_ATTEMPTS:
                task_state.log(
                    f"El Tester falló en el intento {attempt}/"
                    f"{self.MAX_IMPLEMENT_ATTEMPTS}; se vuelve a llamar "
                    "al Implementer para que corrija."
                )

        if memory:
            memory.record_bug(
                description="; ".join(
                    dict.fromkeys(failed_commands_history)
                ),
                resolved=False,
                resolution="",
            )

        task_state.log(
            "Las validaciones del Tester siguieron fallando después de "
            f"{self.MAX_IMPLEMENT_ATTEMPTS} intento(s)."
        )
        return True

    def _run_pipeline(self, task_state: TaskState) -> None:
        for step in ("explorer", "researcher"):
            if not self._try_call(task_state, step):
                return

        explorer_result = task_state.last_result_of("explorer")

        if explorer_result and task_state.project_memory:
            task_state.project_memory.update_from_explorer(
                explorer_result.data
            )

        if not self._run_implement_and_test_cycle(task_state):
            return

        if not self._try_call(task_state, "reviewer"):
            return

        self._finalize_status(task_state)

    @staticmethod
    def _finalize_status(task_state: TaskState) -> None:
        # El loop-detector ya dejó "needs_help" con su propia explicación;
        # no lo pisamos con el resultado genérico de tester/reviewer.
        if task_state.status == "needs_help":
            return

        tester_result = task_state.last_result_of("tester")
        reviewer_result = task_state.last_result_of("reviewer")

        tester_failed = (
            tester_result
            and not tester_result.data.get("all_passed", False)
        )

        reviewer_rejected = (
            reviewer_result
            and not reviewer_result.data.get("approved", False)
        )

        if tester_failed:
            task_state.status = "blocked"
            task_state.log(
                "La ejecución terminó, pero las validaciones fallaron."
            )
        elif reviewer_rejected:
            task_state.status = "blocked"
            task_state.log(
                "La ejecución terminó, pero el Reviewer no aprobó los cambios."
            )
        else:
            task_state.status = "done"
            task_state.log("Tarea completada.")

    def run(
        self,
        user_request: str,
        workspace_path: Optional[str] = None,
    ) -> TaskState:
        workspace = Path(workspace_path or ".").resolve()

        if not workspace.exists():
            raise FileNotFoundError(
                f"El workspace no existe: {workspace}"
            )

        if not workspace.is_dir():
            raise NotADirectoryError(
                f"El workspace no es una carpeta: {workspace}"
            )

        task_state = TaskState(
            original_request=user_request,
            workspace_path=str(workspace),
        )
        task_state.project_memory = ProjectMemory.for_workspace(
            str(workspace)
        )

        task_state.log(f"Workspace: {workspace}")

        # Chequeo temprano: si el workspace no coincide con el que
        # permite agent.config.yaml, cada tool call de cada subagente
        # iba a fallar con PolicyViolation de todos modos -- mejor
        # cortar acá, antes de gastar ni una sola llamada al LLM, que
        # dejar correr el pipeline entero para que no logre nada.
        if self.policy_engine is not None:
            try:
                self.policy_engine.validate_workspace(str(workspace))
            except PolicyViolation as exc:
                task_state.status = "blocked"
                task_state.log(
                    f"Workspace no autorizado por agent.config.yaml: {exc}"
                )
                self._save_memory(task_state)
                return task_state

        try:
            self._run_pipeline(task_state)
        finally:
            self._save_memory(task_state)

        return task_state

    @staticmethod
    def _save_memory(task_state: TaskState) -> None:
        # Best-effort: un fallo al persistir memoria (ej. permisos en
        # memory/) no debe tirar abajo toda la corrida ni ocultar el
        # resultado real de la tarea.
        try:
            task_state.project_memory.record_session(task_state)
            task_state.project_memory.save()
        except Exception as exc:
            task_state.log(
                f"No se pudo guardar la memoria del proyecto: {exc}"
            )
