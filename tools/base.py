"""
Interfaz comun para las tools del sistema.

Esta es la pieza clave del "sistema de plugins para tools" (extra
opcional del TP): cualquier tool nueva se agrega creando UN archivo en
tools/plugins/ que define una instancia de Tool. No hay que tocar
ningun otro archivo del sistema (ni el loader, ni el nucleo del
harness) para que una tool nueva quede disponible -- el loader la
descubre sola.
"""

from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict          # JSON schema de los parametros (formato OpenAI function-calling)
    execute: Callable[..., str]
    category: str              # "read" | "write" | "command" | "network" -- usado por agent.config.yaml
    enabled: bool = True        # permite desactivar una tool sin borrar el archivo

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }