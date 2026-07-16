import subprocess

from tools.base import Tool


def _execute(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        return (
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}\n\n"
            f"RETURN_CODE: {result.returncode}"
        )
    except Exception as e:
        return f"Error running command '{command}': {e}"


TOOL = Tool(
    name="run_command",
    description="Corre un comando de terminal y devuelve stdout/stderr.",
    parameters={
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
    execute=_execute,
    category="command",
)