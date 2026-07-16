"""
Descubre automaticamente las tools disponibles escaneando tools/plugins/.

Agregar una tool nueva al sistema = crear un archivo nuevo ahi que
defina una variable TOOL (instancia de tools.base.Tool). No hay que
tocar este archivo, ni orchestrator.py, ni ningun subagente existente
-- por eso esto cumple con el extra opcional del TP ("permitir agregar
nuevas tools sin modificar el nucleo del harness").

Cada subagente sigue declarando su propia lista ALLOWED_TOOLS (los
NOMBRES de las tools que tiene permitido usar) y arma su subset
llamando a get_tools_for(...) / get_implementations_for(...), igual
que antes -- lo unico que cambio es de donde salen las tools.
"""

import importlib
import pkgutil
from pathlib import Path

from tools.base import Tool

_PLUGINS_PACKAGE = "tools.plugins"


def discover_tools() -> dict:
    """Importa cada modulo dentro de tools/plugins/ y registra su TOOL."""
    tools = {}
    package = importlib.import_module(_PLUGINS_PACKAGE)
    package_path = Path(package.__file__).parent

    for _, module_name, is_pkg in pkgutil.iter_modules([str(package_path)]):
        if is_pkg:
            continue
        module = importlib.import_module(f"{_PLUGINS_PACKAGE}.{module_name}")
        tool = getattr(module, "TOOL", None)
        if tool is None or not isinstance(tool, Tool):
            continue  # el archivo no define una tool valida -- se ignora
        if not tool.enabled:
            continue

        if tool.name in tools:
            raise ValueError(
                f"Hay más de una tool registrada con el nombre '{tool.name}'."
            )

        tools[tool.name] = tool

    return tools


# Se descubren una sola vez, al importar este modulo.
ALL_TOOLS = discover_tools()


def get_tools_for(names: list) -> list:
    """Devuelve la lista de schemas (formato OpenAI) para las tools nombradas."""
    unknown = [n for n in names if n not in ALL_TOOLS]
    if unknown:
        raise ValueError(f"Tools desconocidas o deshabilitadas: {unknown}")
    return [ALL_TOOLS[name].to_openai_schema() for name in names]


def get_implementations_for(names: list) -> dict:
    """Devuelve {nombre: funcion_execute} solo para las tools nombradas."""
    unknown = [n for n in names if n not in ALL_TOOLS]
    if unknown:
        raise ValueError(f"Tools desconocidas o deshabilitadas: {unknown}")
    return {name: ALL_TOOLS[name].execute for name in names}

def get_tool(name: str) -> Tool:
    """Devuelve la instancia completa de una tool registrada."""

    if name not in ALL_TOOLS:
        raise ValueError(
            f"Tool desconocida o deshabilitada: '{name}'."
        )

    return ALL_TOOLS[name]