import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SubagentResult:
    # Resultado que devuelve un subagente al terminar su trabajo
    subagent: str
    summary: str
    data: dict = field(default_factory=dict)
    sources: list = field(default_factory=list)
    timestamp: str = field(default_factory=_now)


class TaskState:

    def __init__(self, original_request: str):
        self.original_request: str = original_request
        self.created_at: str = _now()
        self.status: str = "in_progress"          # in_progress | done | blocked | needs_help
        self.progress_log: list[str] = []          # historial legible de qué se fue haciendo
        self.subagent_results: dict[str, list[SubagentResult]] = {}
        self.sources_consulted: list[str] = []      # acumulado de todas las fuentes usadas
        self.files_modified: list[str] = []
        self.observations: list[str] = []
        self.tool_call_history: list[tuple] = []     # para detección de loops -- (tool_name, args_repr)

    # escritura

    def log(self, message: str) -> None:
        self.progress_log.append(f"[{_now()}] {message}")

    def record_subagent_result(self, result: SubagentResult) -> None:
        self.subagent_results.setdefault(result.subagent, []).append(result)
        self.sources_consulted.extend(result.sources)
        self.log(f"{result.subagent} -> {result.summary}")

    def record_file_modified(self, path: str) -> None:
        if path not in self.files_modified:
            self.files_modified.append(path)

    def record_observation(self, note: str) -> None:
        self.observations.append(note)

    def record_tool_call(self, tool_name: str, args: dict) -> None:
        self.tool_call_history.append((tool_name, json.dumps(args, sort_keys=True)))

    # lectura

    def last_result_of(self, subagent: str) -> Optional[SubagentResult]:
        results = self.subagent_results.get(subagent)
        return results[-1] if results else None

    def is_repeating(self, tool_name: str, args: dict, threshold: int = 2) -> bool:
        key = (tool_name, json.dumps(args, sort_keys=True))
        count = sum(1 for entry in self.tool_call_history if entry == key)
        return count >= threshold

    # serialización

    def to_dict(self) -> dict:
        return {
            "original_request": self.original_request,
            "created_at": self.created_at,
            "status": self.status,
            "progress_log": self.progress_log,
            "subagent_results": {
                name: [asdict(r) for r in results]
                for name, results in self.subagent_results.items()
            },
            "sources_consulted": self.sources_consulted,
            "files_modified": self.files_modified,
            "observations": self.observations,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)