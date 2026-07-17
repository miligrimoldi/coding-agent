import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from project_memory import ProjectMemory


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SubagentResult:
    subagent: str
    summary: str
    data: dict = field(default_factory=dict)
    sources: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now)


class TaskState:
    def __init__(self, original_request: str, workspace_path: str):
        self.original_request = original_request
        self.workspace_path = str(Path(workspace_path).resolve())
        self.created_at = _now()

        # in_progress | done | blocked | needs_help
        self.status = "in_progress"
        self.current_phase: Optional[str] = None

        self.progress_log: list[str] = []
        self.subagent_results: dict[str, list[SubagentResult]] = {}

        # Valores esperados:
        # repository | memory | rag | web | inference
        self.sources_consulted: list[str] = []

        self.files_modified: list[str] = []
        self.observations: list[str] = []

        # Se guarda como diccionario para que sea serializable y auditable.
        self.tool_call_history: list[dict] = []
        self.iterations_by_subagent: dict[str, int] = {}

        # La asigna el Orchestrator al arrancar; puede quedar en None si
        # TaskState se instancia fuera del flujo normal (ej. tests).
        self.project_memory: Optional["ProjectMemory"] = None

    # ---------- Escritura ----------

    def log(self, message: str) -> None:
        self.progress_log.append(f"[{_now()}] {message}")

    def set_phase(self, phase: str) -> None:
        self.current_phase = phase
        self.log(f"Fase actual: {phase}")

    def record_subagent_result(self, result: SubagentResult) -> None:
        self.subagent_results.setdefault(result.subagent, []).append(result)

        for source in result.sources:
            if source not in self.sources_consulted:
                self.sources_consulted.append(source)

        self.log(f"{result.subagent} -> {result.summary}")

    def record_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def record_observation(self, note: str) -> None:
        self.observations.append(note)

    def record_iterations(self, subagent: str, iterations: int) -> None:
        self.iterations_by_subagent[subagent] = iterations

    def record_tool_call(
        self,
        subagent: str,
        tool_name: str,
        args: dict,
        outcome: str = "executed",
        duration_ms: Optional[float] = None,
    ) -> None:
        self.tool_call_history.append({
            "subagent": subagent,
            "tool_name": tool_name,
            "arguments": args,
            "outcome": outcome,
            "duration_ms": duration_ms,
            "timestamp": _now(),
        })

    # ---------- Lectura ----------

    def last_result_of(self, subagent: str) -> Optional[SubagentResult]:
        results = self.subagent_results.get(subagent)
        return results[-1] if results else None

    def is_repeating(
        self,
        subagent: str,
        tool_name: str,
        args: dict,
        threshold: int = 2,
    ) -> bool:
        normalized_args = json.dumps(args, sort_keys=True, default=str)

        count = sum(
            1
            for entry in self.tool_call_history
            if entry["subagent"] == subagent
            and entry["tool_name"] == tool_name
            and json.dumps(
                entry["arguments"],
                sort_keys=True,
                default=str,
            ) == normalized_args
        )

        # threshold=2 permite dos ejecuciones y bloquea la tercera.
        return count >= threshold

    # ---------- Serialización ----------

    def to_dict(self) -> dict:
        return {
            "original_request": self.original_request,
            "workspace_path": self.workspace_path,
            "created_at": self.created_at,
            "status": self.status,
            "current_phase": self.current_phase,
            "progress_log": self.progress_log,
            "subagent_results": {
                name: [asdict(result) for result in results]
                for name, results in self.subagent_results.items()
            },
            "sources_consulted": self.sources_consulted,
            "files_modified": self.files_modified,
            "observations": self.observations,
            "tool_call_history": self.tool_call_history,
            "iterations_by_subagent": self.iterations_by_subagent,
            "project_memory_path": (
                str(self.project_memory.storage_path)
                if self.project_memory
                else None
            ),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            self.to_dict(),
            indent=indent,
            ensure_ascii=False,
            default=str,
        )