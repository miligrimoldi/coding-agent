from tools.base import Tool


def _execute(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except FileNotFoundError:
        return f"Error: File not found at {path}"
    except Exception as e:
        return f"Error reading file {path}: {e}"


TOOL = Tool(
    name="read_file",
    description="Lee el contenido de un archivo dado su path relativo al workspace.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    execute=_execute,
    category="read",
)