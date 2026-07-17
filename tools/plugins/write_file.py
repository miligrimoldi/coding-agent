from pathlib import Path

from tools.base import Tool


def _execute(path: str, content: str) -> str:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote file: {path}"
    except Exception as e:
        return f"Error writing file {path}: {e}"


TOOL = Tool(
    name="write_file",
    description="Escribe contenido en un archivo, reemplazando su contenido actual.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    execute=_execute,
    category="write",
)