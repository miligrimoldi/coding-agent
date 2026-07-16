import json
import shlex
import subprocess
from typing import Optional

from tools.base import Tool


def _execute(
    command: str,
    cwd: Optional[str] = None,
) -> str:
    try:
        command_parts = shlex.split(command)

        if not command_parts:
            return json.dumps({
                "ok": False,
                "stdout": "",
                "stderr": "El comando está vacío.",
                "return_code": None,
                "timed_out": False,
            }, ensure_ascii=False)

        result = subprocess.run(
            command_parts,
            cwd=cwd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return json.dumps({
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "timed_out": False,
        }, ensure_ascii=False)

    except subprocess.TimeoutExpired as exc:
        return json.dumps({
            "ok": False,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "El comando excedió el timeout.",
            "return_code": None,
            "timed_out": True,
        }, ensure_ascii=False)

    except Exception as exc:
        return json.dumps({
            "ok": False,
            "stdout": "",
            "stderr": str(exc),
            "return_code": None,
            "timed_out": False,
        }, ensure_ascii=False)


TOOL = Tool(
    name="run_command",
    description=(
        "Ejecuta un único comando de terminal dentro del workspace "
        "y devuelve stdout, stderr y return code."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string"},
        },
        "required": ["command"],
    },
    execute=_execute,
    category="command",
)