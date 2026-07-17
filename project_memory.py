import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from task_state import TaskState


MEMORY_DIR = Path(__file__).resolve().parent / "memory"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProjectMemory:

    MAX_ITEMS_PER_LIST = 40
    MAX_DECISIONS = 30
    MAX_BUGS = 30
    MAX_SESSION_SUMMARIES = 10

    def __init__(self, workspace_path: str, storage_dir: Path = MEMORY_DIR):
        self.workspace_path = str(Path(workspace_path).resolve())
        self.storage_dir = storage_dir
        self.storage_path = self._build_storage_path()
        self.data = self._load()

    @classmethod
    def for_workspace(cls, workspace_path: str) -> "ProjectMemory":
        return cls(workspace_path)

    def _build_storage_path(self) -> Path:
        digest = hashlib.sha256(
            self.workspace_path.encode("utf-8")
        ).hexdigest()[:12]

        slug = Path(self.workspace_path).name or "workspace"

        return self.storage_dir / f"{slug}-{digest}.json"

    def _load(self) -> dict:
        if not self.storage_path.exists():
            return self._empty()

        try:
            with self.storage_path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError):
            return self._empty()

    def _empty(self) -> dict:
        return {
            "workspace_path": self.workspace_path,
            "created_at": _now(),
            "updated_at": _now(),
            "architecture": {},
            "important_files": [],
            "dependencies": [],
            "useful_commands": {},
            "decisions": [],
            "bugs_investigated": [],
            "session_summaries": [],
        }

    def save(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = _now()

        with self.storage_path.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, indent=2, ensure_ascii=False)

    def has_prior_knowledge(self) -> bool:
        return bool(
            self.data["architecture"]
            or self.data["important_files"]
            or self.data["session_summaries"]
        )

    def as_context(self) -> dict:

        return {
            "architecture": self.data["architecture"],
            "important_files": self.data["important_files"][-20:],
            "dependencies": self.data["dependencies"][-20:],
            "useful_commands": self.data["useful_commands"],
            "recent_decisions": self.data["decisions"][-5:],
            "recent_bugs": self.data["bugs_investigated"][-5:],
            "recent_sessions": self.data["session_summaries"][-3:],
        }

    def update_from_explorer(self, explorer_data: dict) -> None:
        if not isinstance(explorer_data, dict):
            return

        architecture_fields = ("lenguaje", "framework", "estructura")

        architecture = {
            field: explorer_data[field]
            for field in architecture_fields
            if explorer_data.get(field)
        }

        if architecture:
            self.data["architecture"].update(architecture)

        self._merge_unique_list(
            "important_files",
            explorer_data.get("archivos_relevantes", []),
        )

        self._merge_unique_list(
            "dependencies",
            explorer_data.get("dependencias_detectadas", []),
        )

    def update_useful_commands(self, validated_commands: dict) -> None:
        if not isinstance(validated_commands, dict):
            return

        self.data["useful_commands"].update(validated_commands)

    def record_decision(
        self,
        *,
        request: str,
        summary: str,
        files: list[str],
    ) -> None:
        self.data["decisions"].append({
            "timestamp": _now(),
            "request": request,
            "summary": summary,
            "files": files,
        })

        self.data["decisions"] = (
            self.data["decisions"][-self.MAX_DECISIONS:]
        )

    def record_bug(
        self,
        *,
        description: str,
        resolved: bool,
        resolution: str = "",
    ) -> None:
        if not description:
            return

        self.data["bugs_investigated"].append({
            "timestamp": _now(),
            "description": description,
            "resolved": resolved,
            "resolution": resolution,
        })

        self.data["bugs_investigated"] = (
            self.data["bugs_investigated"][-self.MAX_BUGS:]
        )

    def record_session(self, task_state: "TaskState") -> None:
        self.data["session_summaries"].append({
            "timestamp": _now(),
            "request": task_state.original_request,
            "status": task_state.status,
            "files_modified": list(task_state.files_modified),
        })

        self.data["session_summaries"] = (
            self.data["session_summaries"][-self.MAX_SESSION_SUMMARIES:]
        )

    def _merge_unique_list(self, key: str, new_items) -> None:
        if not isinstance(new_items, list):
            return

        existing = self.data[key]

        for item in new_items:
            if isinstance(item, str) and item not in existing:
                existing.append(item)

        self.data[key] = existing[-self.MAX_ITEMS_PER_LIST:]
