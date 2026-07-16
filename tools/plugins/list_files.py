"""Tool: list_files -- lista archivos y carpetas dentro de un directorio."""

import os

from tools.base import Tool


def _execute(path: str = ".") -> str:
    try:
        items = os.listdir(path)
        return "\n".join(sorted(items))
    except Exception as e:
        return f"Error listing files in {path}: {e}"


TOOL = Tool(
    name="list_files",
    description="Lista los archivos y carpetas dentro de un directorio.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    execute=_execute,
    category="read",
)