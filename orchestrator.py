import hashlib
import json
import re
from pathlib import Path
from typing import Optional

from observability import get_observability
from policy_engine import (
    PolicyEngine,
    PolicyViolation,
)
from project_memory import ProjectMemory
from request_mode import (
    RequestMode,
    detect_request_mode,
)
from task_state import (
    TaskState,
    SubagentResult,
)
from subagents.subagent_protocol import (
    Subagent,
)


_LINE_COLUMN_PATTERN = re.compile(
    r"\b\d+:\d+\b"
)

_WHITESPACE_PATTERN = re.compile(
    r"\s+"
)


_SUBAGENT_PHASES = {
    "explorer": "exploration",
    "researcher": "research",
    "implementer": "implementation",
    "tester": "testing",
    "reviewer": "review",
}


class SubagentError(Exception):
    pass


class Orchestrator:
    MAX_IMPLEMENT_ATTEMPTS = 3

    def __init__(
        self,
        policy_engine: Optional[
            PolicyEngine
        ] = None,
    ):
        self.subagents: dict[
            str,
            Subagent,
        ] = {}

        self.policy_engine = (
            policy_engine
        )

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
        """
        Ejecuta un subagente dentro de una observación Langfuse.

        Las generaciones OpenAI y las tools ejecutadas por ese
        subagente quedan automáticamente anidadas dentro del span.
        """

        if name not in self.subagents:
            raise SubagentError(
                f"Subagente '{name}' no está "
                "registrado."
            )

        task_state.log(
            f"Llamando a subagente: {name}"
        )

        request_mode = (
            detect_request_mode(
                task_state.original_request
            ).value
        )

        phase = _SUBAGENT_PHASES.get(
            name,
            name,
        )

        observability = (
            get_observability()
        )

        with observability.subagent_span(
            subagent=name,
            phase=phase,
            request_mode=request_mode,
        ) as subagent_observation:
            try:
                result = self.subagents[
                    name
                ].run(task_state)

            except Exception as exc:
                task_state.record_observation(
                    f"Falló el subagente "
                    f"{name}: {exc}"
                )

                raise SubagentError(
                    f"El subagente {name} "
                    f"falló: {exc}"
                ) from exc

            task_state.record_subagent_result(
                result
            )

            subagent_observation.update(
                output=(
                    observability
                    .build_subagent_output(
                        result=result,
                        task_state=task_state,
                    )
                ),
                metadata={
                    "subagent": name,
                    "phase": phase,
                    "requestmode": (
                        request_mode
                    ),
                    "status": (
                        task_state.status
                    ),
                },
            )

            return result

    def _try_call(
        self,
        task_state: TaskState,
        step: str,
    ) -> bool:
        try:
            self.call_subagent(
                step,
                task_state,
            )

            return True

        except SubagentError as exc:
            task_state.status = "blocked"

            task_state.log(
                "Tarea bloqueada en el paso "
                f"'{step}': {exc}"
            )

            return False

    @staticmethod
    def _fingerprint_failures(
        failing_checks: list[dict],
    ) -> Optional[str]:
        """
        Construye una firma de los errores reales del Tester.

        Incluye stdout y stderr porque herramientas como ESLint
        suelen escribir sus errores en stdout.

        Solo normaliza números de línea y columna. Conserva otros
        números relevantes, como la cantidad de errores reportados.
        """

        if not failing_checks:
            return None

        normalized_checks: list[dict] = []

        for check in sorted(
            failing_checks,
            key=lambda item: str(
                item.get("command", "")
            ),
        ):
            stdout = str(
                check.get("stdout", "")
            ).strip()

            stderr = str(
                check.get("stderr", "")
            ).strip()

            output_parts: list[str] = []

            if stdout:
                output_parts.append(stdout)

            if stderr and stderr != stdout:
                output_parts.append(stderr)

            combined_output = "\n".join(
                output_parts
            )

            normalized_output = (
                _LINE_COLUMN_PATTERN.sub(
                    "<line:column>",
                    combined_output,
                )
            )

            normalized_output = (
                _WHITESPACE_PATTERN.sub(
                    " ",
                    normalized_output,
                ).strip()
            )

            normalized_checks.append({
                "command": check.get(
                    "command",
                    "",
                ),
                "return_code": check.get(
                    "return_code",
                ),
                "timed_out": bool(
                    check.get(
                        "timed_out",
                        False,
                    )
                ),
                "output": normalized_output[
                    -6000:
                ],
            })

        serialized = json.dumps(
            normalized_checks,
            ensure_ascii=False,
            sort_keys=True,
        )

        return hashlib.sha256(
            serialized.encode("utf-8")
        ).hexdigest()

    def _run_implement_and_test_cycle(
        self,
        task_state: TaskState,
    ) -> bool:
        memory = (
            task_state.project_memory
        )

        failed_commands_history: list[
            str
        ] = []

        previous_fingerprint: Optional[
            str
        ] = None

        for attempt in range(
            1,
            self.MAX_IMPLEMENT_ATTEMPTS
            + 1,
        ):
            task_state.log(
                "Intento de implementación: "
                f"{attempt}/"
                f"{self.MAX_IMPLEMENT_ATTEMPTS}"
            )

            if not self._try_call(
                task_state,
                "implementer",
            ):
                return False

            implementer_result = (
                task_state.last_result_of(
                    "implementer"
                )
            )

            implementer_declined = bool(
                implementer_result
                and implementer_result.data.get(
                    "evidence_sufficient"
                )
                is False
                and not task_state.files_modified
            )

            if implementer_declined:
                risks_or_notes = (
                    implementer_result.data.get(
                        "risks_or_notes",
                        [],
                    )
                )

                if not isinstance(
                    risks_or_notes,
                    list,
                ):
                    risks_or_notes = []

                reasons = "; ".join(
                    str(note)
                    for note
                    in risks_or_notes
                ) or (
                    implementer_result.data.get(
                        "summary",
                        "",
                    )
                )

                task_state.status = (
                    "needs_help"
                )

                task_state.log(
                    "El Implementer no encontró "
                    "evidencia suficiente para "
                    "aplicar el pedido de forma "
                    "segura y no modificó archivos."
                )

                task_state.record_observation(
                    "Implementer declinó actuar: "
                    f"{reasons}"
                )

                if memory:
                    memory.record_bug(
                        description=(
                            "Pedido no resuelto por "
                            "falta de evidencia o "
                            f"definiciones: {reasons}"
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

            tester_result = (
                task_state.last_result_of(
                    "tester"
                )
            )

            if tester_result is None:
                task_state.status = (
                    "blocked"
                )

                task_state.log(
                    "No existe resultado del "
                    "Tester."
                )

                return True

            validated_commands = (
                tester_result.data.get(
                    "validated_commands",
                    {},
                )
            )

            if (
                memory
                and validated_commands
            ):
                memory.update_useful_commands(
                    validated_commands
                )

            if tester_result.data.get(
                "all_passed",
                False,
            ):
                if (
                    memory
                    and failed_commands_history
                ):
                    memory.record_bug(
                        description="; ".join(
                            dict.fromkeys(
                                failed_commands_history
                            )
                        ),
                        resolved=True,
                        resolution=(
                            "Resuelto en el intento "
                            f"{attempt}."
                        ),
                    )

                return True

            failing_checks = [
                check
                for check
                in tester_result.data.get(
                    "checks",
                    [],
                )
                if not check.get(
                    "ok",
                    False,
                )
            ]

            failed_commands_history.extend(
                check["command"]
                for check
                in failing_checks
                if "command" in check
            )

            fingerprint = (
                self._fingerprint_failures(
                    failing_checks
                )
            )

            if (
                previous_fingerprint is not None
                and fingerprint is not None
                and fingerprint
                != previous_fingerprint
            ):
                task_state.log(
                    "El Tester continúa reportando "
                    "fallas, pero el detalle cambió "
                    "respecto del intento anterior. "
                    "Se considera que hubo progreso "
                    "y se permite otro reintento."
                )

            if (
                fingerprint is not None
                and fingerprint
                == previous_fingerprint
            ):
                task_state.status = (
                    "needs_help"
                )

                task_state.log(
                    "Loop detectado: el Tester "
                    "volvió a fallar igual que "
                    "en el intento anterior "
                    f"(intento {attempt})."
                )

                command_names = ", ".join(
                    dict.fromkeys(
                        check.get(
                            "command",
                            "",
                        )
                        for check
                        in failing_checks
                        if check.get(
                            "command"
                        )
                    )
                )

                task_state.record_observation(
                    "Loop de reintentos sin "
                    "avance. Comandos: "
                    f"{command_names}"
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
                            "Loop detectado: mismo "
                            "error repetido sin "
                            "progreso."
                        ),
                    )

                return True

            previous_fingerprint = (
                fingerprint
            )

            if (
                attempt
                < self.MAX_IMPLEMENT_ATTEMPTS
            ):
                task_state.log(
                    "El Tester falló en el "
                    f"intento {attempt}/"
                    f"{self.MAX_IMPLEMENT_ATTEMPTS}; "
                    "se vuelve a llamar al "
                    "Implementer."
                )

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
            "Las validaciones siguieron "
            "fallando después de "
            f"{self.MAX_IMPLEMENT_ATTEMPTS} "
            "intento(s)."
        )

        return True

    def _run_pipeline(
        self,
        task_state: TaskState,
    ) -> None:
        request_mode = (
            detect_request_mode(
                task_state.original_request
            )
        )

        task_state.log(
            "Modo de tarea detectado: "
            f"{request_mode.value}"
        )

        # Todos los modos comienzan entendiendo el repositorio.
        if not self._try_call(
            task_state,
            "explorer",
        ):
            return

        explorer_result = (
            task_state.last_result_of(
                "explorer"
            )
        )

        if (
            explorer_result
            and task_state.project_memory
        ):
            task_state.project_memory.update_from_explorer(
                explorer_result.data
            )

        # Una descripción pura se resuelve con Explorer.
        if (
            request_mode
            == RequestMode.DESCRIPTION
        ):
            self._finalize_description(
                task_state,
                explorer_result,
            )

            return

        # Análisis e implementación requieren Researcher.
        if not self._try_call(
            task_state,
            "researcher",
        ):
            return

        researcher_result = (
            task_state.last_result_of(
                "researcher"
            )
        )

        if researcher_result is None:
            task_state.status = "blocked"

            task_state.log(
                "No existe resultado del "
                "Researcher."
            )

            return

        # Un análisis termina después del Researcher.
        if (
            request_mode
            == RequestMode.ANALYSIS
        ):
            self._finalize_analysis(
                task_state,
                researcher_result,
            )

            return

        # Desde aquí el modo es implementation.
        requirements_unclear = bool(
            researcher_result.data.get(
                "requirements_clear"
            )
            is False
        )

        if requirements_unclear:
            clarifications = (
                researcher_result.data.get(
                    "clarifications_needed",
                    [],
                )
            )

            if not isinstance(
                clarifications,
                list,
            ):
                clarifications = []

            clarification_text = "; ".join(
                str(item)
                for item in clarifications
                if item
            )

            if not clarification_text:
                clarification_text = (
                    "El Researcher determinó "
                    "que faltan definiciones "
                    "funcionales."
                )

            task_state.status = (
                "needs_help"
            )

            task_state.log(
                "El pedido requiere "
                "aclaraciones funcionales "
                "antes de modificar el "
                "repositorio."
            )

            task_state.record_observation(
                "Aclaraciones requeridas: "
                f"{clarification_text}"
            )

            return

        if not (
            self
            ._run_implement_and_test_cycle(
                task_state
            )
        ):
            return

        if (
            task_state.status
            == "needs_help"
        ):
            return

        if not self._try_call(
            task_state,
            "reviewer",
        ):
            return

        tester_result = (
            task_state.last_result_of(
                "tester"
            )
        )

        reviewer_result = (
            task_state.last_result_of(
                "reviewer"
            )
        )

        implementer_result = (
            task_state.last_result_of(
                "implementer"
            )
        )

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
            )
            is True
            and task_state.files_modified
        )

        if should_record_decision:
            task_state.project_memory.record_decision(
                request=(
                    task_state.original_request
                ),
                summary=(
                    implementer_result.data.get(
                        "summary",
                        "",
                    )
                ),
                files=list(
                    task_state.files_modified
                ),
            )

        self._finalize_status(
            task_state
        )

    @staticmethod
    def _finalize_description(
        task_state: TaskState,
        explorer_result: Optional[
            SubagentResult
        ],
    ) -> None:
        if explorer_result is None:
            task_state.status = (
                "needs_help"
            )

            task_state.log(
                "No existe evidencia del "
                "Explorer para responder la "
                "descripción."
            )

            return

        data = explorer_result.data

        files_read = data.get(
            "archivos_leidos",
            [],
        )

        summary = data.get(
            "resumen_para_usuario",
            "",
        )

        current_flow = data.get(
            "flujo_actual",
            [],
        )

        has_evidence = bool(
            isinstance(
                files_read,
                list,
            )
            and files_read
            and (
                (
                    isinstance(
                        summary,
                        str,
                    )
                    and summary.strip()
                )
                or (
                    isinstance(
                        current_flow,
                        list,
                    )
                    and current_flow
                )
            )
        )

        if has_evidence:
            task_state.status = "done"

            task_state.log(
                "Descripción completada por "
                "el Explorer sin modificar "
                "archivos."
            )

        else:
            task_state.status = (
                "needs_help"
            )

            task_state.log(
                "El Explorer no reunió "
                "evidencia suficiente para "
                "completar la descripción."
            )

    @staticmethod
    def _finalize_analysis(
        task_state: TaskState,
        researcher_result: SubagentResult,
    ) -> None:
        evidence_sufficient = bool(
            researcher_result.data.get(
                "evidence_sufficient"
            )
            is True
        )

        current_implementation = (
            researcher_result.data.get(
                "current_implementation",
                [],
            )
        )

        findings = (
            researcher_result.data.get(
                "findings",
                [],
            )
        )

        suggested_improvements = (
            researcher_result.data.get(
                "suggested_improvements",
                [],
            )
        )

        has_content = bool(
            (
                isinstance(
                    current_implementation,
                    list,
                )
                and current_implementation
            )
            or (
                isinstance(
                    findings,
                    list,
                )
                and findings
            )
            or (
                isinstance(
                    suggested_improvements,
                    list,
                )
                and suggested_improvements
            )
        )

        if (
            evidence_sufficient
            and has_content
        ):
            task_state.status = "done"

            task_state.log(
                "Análisis completado sin "
                "modificar el repositorio."
            )

            return

        risks = (
            researcher_result.data.get(
                "risks_or_unknowns",
                [],
            )
        )

        if not isinstance(
            risks,
            list,
        ):
            risks = []

        reason = "; ".join(
            str(item)
            for item in risks
            if item
        )

        if not reason:
            reason = (
                "El Researcher no reunió "
                "evidencia suficiente."
            )

        task_state.status = (
            "needs_help"
        )

        task_state.log(
            "No hubo evidencia suficiente "
            "para completar el análisis."
        )

        task_state.record_observation(
            f"Análisis incompleto: "
            f"{reason}"
        )

    @staticmethod
    def _finalize_status(
        task_state: TaskState,
    ) -> None:
        if (
            task_state.status
            == "needs_help"
        ):
            return

        tester_result = (
            task_state.last_result_of(
                "tester"
            )
        )

        reviewer_result = (
            task_state.last_result_of(
                "reviewer"
            )
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
                "La ejecución terminó, "
                "pero las validaciones "
                "fallaron."
            )

        elif reviewer_rejected:
            task_state.status = "blocked"

            task_state.log(
                "La ejecución terminó, "
                "pero el Reviewer no aprobó "
                "los cambios."
            )

        else:
            task_state.status = "done"

            task_state.log(
                "Tarea completada."
            )

    def run(
        self,
        user_request: str,
        workspace_path: Optional[
            str
        ] = None,
    ) -> TaskState:
        workspace = Path(
            workspace_path or "."
        ).resolve()

        if not workspace.exists():
            raise FileNotFoundError(
                "El workspace no existe: "
                f"{workspace}"
            )

        if not workspace.is_dir():
            raise NotADirectoryError(
                "El workspace no es una "
                f"carpeta: {workspace}"
            )

        request_mode = (
            detect_request_mode(
                user_request
            )
        )

        task_state = TaskState(
            original_request=user_request,
            workspace_path=str(
                workspace
            ),
        )

        task_state.project_memory = (
            ProjectMemory.for_workspace(
                str(workspace)
            )
        )

        task_state.log(
            f"Workspace: {workspace}"
        )

        observability = (
            get_observability()
        )

        with observability.run_span(
            user_request=user_request,
            workspace_path=str(
                workspace
            ),
            request_mode=(
                request_mode.value
            ),
        ) as run_observation:
            try:
                # Valida el workspace antes de gastar llamadas
                # innecesarias al modelo.
                if (
                    self.policy_engine
                    is not None
                ):
                    try:
                        (
                            self.policy_engine
                            .validate_workspace(
                                str(workspace)
                            )
                        )

                    except (
                        PolicyViolation
                    ) as exc:
                        task_state.status = (
                            "blocked"
                        )

                        task_state.log(
                            "Workspace no "
                            "autorizado por "
                            "agent.config.yaml: "
                            f"{exc}"
                        )

                        return task_state

                self._run_pipeline(
                    task_state
                )

                return task_state

            finally:
                # La memoria se guarda antes de construir el output
                # para que cualquier error de persistencia también
                # quede visible en la traza.
                self._save_memory(
                    task_state
                )

                run_output = (
                    observability
                    .build_run_output(
                        task_state
                    )
                )

                run_output[
                    "request_mode"
                ] = request_mode.value

                run_observation.update(
                    output=run_output,
                    metadata={
                        "requestmode": (
                            request_mode.value
                        ),
                        "status": (
                            task_state.status
                        ),
                        "workspace": (
                            workspace.name
                        ),
                        "subagentcount": len(
                            task_state
                            .subagent_results
                        ),
                        "modifiedfilescount": len(
                            task_state
                            .files_modified
                        ),
                    },
                    level=(
                        "ERROR"
                        if (
                            task_state.status
                            == "blocked"
                        )
                        else "DEFAULT"
                    ),
                    status_message=(
                        f"Final status: "
                        f"{task_state.status}"
                    ),
                )

    @staticmethod
    def _save_memory(
        task_state: TaskState,
    ) -> None:
        try:
            if (
                task_state.project_memory
                is None
            ):
                return

            task_state.project_memory.record_session(
                task_state
            )

            task_state.project_memory.save()

        except Exception as exc:
            task_state.log(
                "No se pudo guardar la "
                "memoria del proyecto: "
                f"{exc}"
            )