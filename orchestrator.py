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
    # Intentos totales del ciclo implementer -> tester:
    # un intento inicial y hasta dos reintentos.
    MAX_IMPLEMENT_ATTEMPTS = 3

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
    ):
        self.subagents: dict[str, Subagent] = {}

        # Es opcional porque algunos tests unitarios pueden usar
        # subagentes falsos sin necesidad de cargar políticas.
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
        Llama a un subagente.

        Si el subagente falla con una excepción, marca la tarea como
        bloqueada y devuelve False para indicar que hay que detener
        el pipeline.
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
    def _fingerprint_failures(
        failing_checks: list[dict],
    ) -> Optional[str]:
        """
        Genera una huella de los errores del Tester.

        Normaliza números que pueden cambiar entre ejecuciones, como
        tiempos o números de línea, para detectar si dos intentos
        consecutivos fallaron esencialmente de la misma manera.
        """

        if not failing_checks:
            return None

        parts = []

        for check in sorted(
            failing_checks,
            key=lambda item: item["command"],
        ):
            normalized_stderr = _DIGITS_PATTERN.sub(
                "#",
                check.get("stderr", ""),
            )[:300]

            parts.append(
                f"{check['command']}|"
                f"{check.get('return_code')}|"
                f"{normalized_stderr}"
            )

        return hashlib.sha256(
            "\n".join(parts).encode("utf-8")
        ).hexdigest()

    def _run_implement_and_test_cycle(
        self,
        task_state: TaskState,
    ) -> bool:
        """
        Ejecuta el ciclo Implementer -> Tester.

        Si el Tester falla, vuelve a llamar al Implementer para que
        corrija usando como contexto los errores de la validación
        anterior.

        Si el Implementer declara que no tiene evidencia suficiente y
        no modificó archivos, la tarea queda en needs_help y el Tester
        no se ejecuta.

        Si dos intentos consecutivos fallan con el mismo error, se
        detecta un ciclo sin progreso y la tarea queda en needs_help.

        También actualiza la memoria con comandos validados y bugs
        investigados. La decisión exitosa se guarda más adelante,
        después de que el Reviewer aprueba los cambios.

        Devuelve False solamente cuando un subagente falla con una
        excepción. En los demás casos devuelve True.
        """

        memory = task_state.project_memory
        failed_commands_history: list[str] = []
        previous_fingerprint: Optional[str] = None

        for attempt in range(
            1,
            self.MAX_IMPLEMENT_ATTEMPTS + 1,
        ):
            if not self._try_call(
                task_state,
                "implementer",
            ):
                return False

            implementer_result = task_state.last_result_of(
                "implementer"
            )

            implementer_declined = bool(
                implementer_result
                and implementer_result.data.get(
                    "evidence_sufficient"
                ) is False
                and not task_state.files_modified
            )

            # Si el Implementer no pudo actuar, no tiene sentido
            # ejecutar el Tester ni iniciar nuevos intentos.
            if implementer_declined:
                risks_or_notes = implementer_result.data.get(
                    "risks_or_notes",
                    [],
                )

                if not isinstance(risks_or_notes, list):
                    risks_or_notes = []

                reasons = "; ".join(
                    str(note)
                    for note in risks_or_notes
                ) or implementer_result.data.get(
                    "summary",
                    "",
                )

                task_state.status = "needs_help"

                task_state.log(
                    "El Implementer no encontró evidencia suficiente "
                    "para aplicar el pedido de forma segura y no "
                    "modificó ningún archivo."
                )

                task_state.record_observation(
                    f"Implementer declinó actuar: {reasons}"
                )

                if memory:
                    memory.record_bug(
                        description=(
                            "Pedido no resuelto por falta de "
                            f"evidencia o definiciones: {reasons}"
                        ),
                        resolved=False,
                        resolution="",
                    )

                return True

            if not self._try_call(
                task_state,
                "tester",
            ):
                return False

            tester_result = task_state.last_result_of(
                "tester"
            )

            validated_commands = tester_result.data.get(
                "validated_commands",
                {},
            )

            if memory and validated_commands:
                memory.update_useful_commands(
                    validated_commands
                )

            # Si todas las validaciones pasaron, termina el ciclo.
            if tester_result.data.get(
                "all_passed",
                False,
            ):
                if memory and failed_commands_history:
                    memory.record_bug(
                        description="; ".join(
                            dict.fromkeys(
                                failed_commands_history
                            )
                        ),
                        resolved=True,
                        resolution=(
                            f"Resuelto en el intento {attempt}."
                        ),
                    )

                return True

            failing_checks = [
                check
                for check in tester_result.data.get(
                    "checks",
                    [],
                )
                if not check.get("ok", False)
            ]

            failed_commands_history.extend(
                check["command"]
                for check in failing_checks
            )

            fingerprint = self._fingerprint_failures(
                failing_checks
            )

            # Si el error es igual al del intento anterior, se corta
            # para evitar reintentos sin progreso.
            if (
                fingerprint is not None
                and fingerprint == previous_fingerprint
            ):
                task_state.status = "needs_help"

                task_state.log(
                    "Loop detectado: el Tester volvió a fallar "
                    "exactamente igual que en el intento anterior "
                    f"(intento {attempt}). El Implementer no está "
                    "progresando."
                )

                failing_command_names = ", ".join(
                    dict.fromkeys(
                        check["command"]
                        for check in failing_checks
                    )
                )

                task_state.record_observation(
                    "Loop de reintentos sin avance: los comandos "
                    f"'{failing_command_names}' siguen fallando con "
                    "el mismo error. Hace falta intervención humana "
                    "para diagnosticar la causa."
                )

                if memory:
                    memory.record_bug(
                        description="; ".join(
                            dict.fromkeys(
                                failed_commands_history
                            )
                        ),
                        resolved=False,
                        resolution=(
                            "Loop detectado: mismo error repetido "
                            "sin progreso entre intentos."
                        ),
                    )

                return True

            previous_fingerprint = fingerprint

            if attempt < self.MAX_IMPLEMENT_ATTEMPTS:
                task_state.log(
                    f"El Tester falló en el intento {attempt}/"
                    f"{self.MAX_IMPLEMENT_ATTEMPTS}; se vuelve a "
                    "llamar al Implementer para que corrija."
                )

        # Se agotaron todos los intentos sin resolver los errores.
        if memory:
            memory.record_bug(
                description="; ".join(
                    dict.fromkeys(
                        failed_commands_history
                    )
                ),
                resolved=False,
                resolution="",
            )

        task_state.log(
            "Las validaciones del Tester siguieron fallando "
            f"después de {self.MAX_IMPLEMENT_ATTEMPTS} "
            "intento(s)."
        )

        return True

    def _run_pipeline(
        self,
        task_state: TaskState,
    ) -> None:
        for step in (
            "explorer",
            "researcher",
        ):
            if not self._try_call(
                task_state,
                step,
            ):
                return

        explorer_result = task_state.last_result_of(
            "explorer"
        )

        if explorer_result and task_state.project_memory:
            task_state.project_memory.update_from_explorer(
                explorer_result.data
            )

        if not self._run_implement_and_test_cycle(
            task_state
        ):
            return

        # Si el Implementer declinó o se detectó un loop,
        # no se ejecuta el Reviewer.
        if task_state.status == "needs_help":
            return

        if not self._try_call(
            task_state,
            "reviewer",
        ):
            return

        tester_result = task_state.last_result_of(
            "tester"
        )
        reviewer_result = task_state.last_result_of(
            "reviewer"
        )
        implementer_result = task_state.last_result_of(
            "implementer"
        )

        # La decisión se guarda únicamente cuando hubo una
        # implementación real, el Tester pasó y el Reviewer aprobó.
        should_record_decision = bool(
            task_state.project_memory
            and tester_result
            and tester_result.data.get(
                "all_passed",
                False,
            )
            and reviewer_result
            and reviewer_result.data.get(
                "approved",
                False,
            )
            and implementer_result
            and implementer_result.data.get(
                "evidence_sufficient"
            ) is True
            and task_state.files_modified
        )

        if should_record_decision:
            task_state.project_memory.record_decision(
                request=task_state.original_request,
                summary=implementer_result.data.get(
                    "summary",
                    "",
                ),
                files=list(task_state.files_modified),
            )

        self._finalize_status(task_state)

    @staticmethod
    def _finalize_status(
        task_state: TaskState,
    ) -> None:
        # Los casos de falta de evidencia o loops ya quedaron
        # marcados y no deben sobrescribirse.
        if task_state.status == "needs_help":
            return

        tester_result = task_state.last_result_of(
            "tester"
        )
        reviewer_result = task_state.last_result_of(
            "reviewer"
        )

        tester_failed = bool(
            tester_result
            and not tester_result.data.get(
                "all_passed",
                False,
            )
        )

        reviewer_rejected = bool(
            reviewer_result
            and not reviewer_result.data.get(
                "approved",
                False,
            )
        )

        if tester_failed:
            task_state.status = "blocked"
            task_state.log(
                "La ejecución terminó, pero las "
                "validaciones fallaron."
            )
        elif reviewer_rejected:
            task_state.status = "blocked"
            task_state.log(
                "La ejecución terminó, pero el Reviewer "
                "no aprobó los cambios."
            )
        else:
            task_state.status = "done"
            task_state.log("Tarea completada.")

    def run(
        self,
        user_request: str,
        workspace_path: Optional[str] = None,
    ) -> TaskState:
        workspace = Path(
            workspace_path or "."
        ).resolve()

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

        task_state.project_memory = (
            ProjectMemory.for_workspace(
                str(workspace)
            )
        )

        task_state.log(
            f"Workspace: {workspace}"
        )

        # Valida el workspace antes de gastar llamadas al LLM.
        if self.policy_engine is not None:
            try:
                self.policy_engine.validate_workspace(
                    str(workspace)
                )
            except PolicyViolation as exc:
                task_state.status = "blocked"
                task_state.log(
                    "Workspace no autorizado por "
                    f"agent.config.yaml: {exc}"
                )

                self._save_memory(task_state)
                return task_state

        try:
            self._run_pipeline(task_state)
        finally:
            self._save_memory(task_state)

        return task_state

    @staticmethod
    def _save_memory(
        task_state: TaskState,
    ) -> None:
        # Un error al guardar memoria no debe ocultar el
        # resultado principal de la ejecución.
        try:
            task_state.project_memory.record_session(
                task_state
            )
            task_state.project_memory.save()
        except Exception as exc:
            task_state.log(
                "No se pudo guardar la memoria "
                f"del proyecto: {exc}"
            )