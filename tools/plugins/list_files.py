import os

from tools.base import Tool


def _execute(path: str = ".") -> str:
    try:
        entries = []

        with os.scandir(path) as it:
            for entry in it:
                name = entry.name

                if entry.is_dir():
                    name += "/"

                entries.append(name)

        return "\n".join(sorted(entries))
    except Exception as e:
        return f"Error listing files in {path}: {e}"


TOOL = Tool(
    name="list_files",
    description=(
        "Lista los archivos y carpetas dentro de un directorio. Las "
        "carpetas se marcan con una '/' al final del nombre."
    ),
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    execute=_execute,
    category="read",
)