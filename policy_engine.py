from copy import deepcopy
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

import yaml

from tools.base import Tool


class PolicyViolation(Exception):
    pass


@dataclass
class PolicyDecision:
    """
    Resultado de validar una tool call.

    arguments:
        Argumentos normalizados que se pueden enviar a la implementación.

    requires_approval:
        Indica si hay que consultar al usuario antes de ejecutar.

    approval_reason:
        Explica por qué se requiere aprobación.
    """

    arguments: dict
    requires_approval: bool = False
    approval_reason: str = ""


class PolicyEngine:
    """
    Analiza las reglas de agent.config.yaml y decide si una tool call:

    - puede ejecutarse;
    - está prohibida;
    - necesita aprobación;
    - debe recibir argumentos normalizados.
    """

    PATH_TOOLS = {
        "read_file",
        "write_file",
        "list_files",
    }

    FORBIDDEN_SHELL_OPERATORS = (
        "&&",
        "||",
        ";",
        "|",
        "`",
        "$(",
    )

    def __init__(self, config: dict):
        self.config = config

    @classmethod
    def from_file(
        cls,
        path: str = "agent.config.yaml",
    ) -> "PolicyEngine":
        """
        Carga las políticas desde un archivo YAML.
        """

        config_path = Path(path)

        if not config_path.exists():
            raise FileNotFoundError(
                f"No se encontró el archivo de configuración: {path}"
            )

        with config_path.open("r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}

        return cls(config)

    def validate_workspace(self, workspace_path: str) -> None:
        """
        Chequea que workspace_path sea el workspace configurado en
        agent.config.yaml (si hay uno configurado). Público para poder
        validarlo de entrada, antes de arrancar el pipeline -- ver
        Orchestrator.run().
        """
        configured_workspace = self.config.get("workspace")

        if not configured_workspace:
            return

        allowed_workspace = Path(configured_workspace).resolve()
        requested_workspace = Path(workspace_path).resolve()

        if requested_workspace != allowed_workspace:
            raise PolicyViolation(
                f"El workspace '{requested_workspace}' no coincide con "
                f"el workspace permitido '{allowed_workspace}'."
            )

    def validate(
        self,
        tool: Tool,
        arguments: dict,
        workspace_path: str,
    ) -> PolicyDecision:
        """
        Valida una tool antes de ejecutarla.
        """

        self.validate_workspace(workspace_path)
        normalized_arguments = deepcopy(arguments)
        requires_approval = False
        reasons: list[str] = []

        # Tools que reciben un path.
        if tool.name in self.PATH_TOOLS:
            normalized_arguments = self._validate_path_tool(
                tool=tool,
                arguments=normalized_arguments,
                workspace_path=workspace_path,
            )

        # Tools que ejecutan comandos.
        if tool.category == "command":
            command = normalized_arguments.get("command", "")

            self._validate_command(command)

            approval_commands = (
                self.config
                .get("commands", {})
                .get("require_approval", [])
            )

            if self._contains_any(command, approval_commands):
                requires_approval = True
                reasons.append(
                    "El comando coincide con una regla de aprobación: "
                    f"{command}"
                )

        # Categorías que requieren aprobación.
        approval_categories = (
            self.config
            .get("approval", {})
            .get("categories", [])
        )

        if tool.category in approval_categories:
            requires_approval = True
            reasons.append(
                f"La categoría '{tool.category}' requiere aprobación."
            )

        return PolicyDecision(
            arguments=normalized_arguments,
            requires_approval=requires_approval,
            approval_reason=" ".join(reasons),
        )

    def _validate_path_tool(
        self,
        tool: Tool,
        arguments: dict,
        workspace_path: str,
    ) -> dict:
        """
        Comprueba que el path esté dentro del workspace y que no coincida
        con una regla de bloqueo.
        """

        path_argument = arguments.get("path")

        if not isinstance(path_argument, str) or not path_argument.strip():
            raise PolicyViolation(
                f"La tool '{tool.name}' requiere un path válido."
            )

        workspace = Path(workspace_path).resolve()
        candidate = (workspace / path_argument).resolve()

        try:
            relative_path = candidate.relative_to(workspace).as_posix()
        except ValueError as exc:
            raise PolicyViolation(
                f"El path '{path_argument}' está fuera del workspace."
            ) from exc

        permission_type = (
            "write"
            if tool.category == "write"
            else "read"
        )

        denied_patterns = (
            self.config
            .get("permissions", {})
            .get(permission_type, {})
            .get("deny", [])
        )

        for pattern in denied_patterns:
            if self._matches_path(relative_path, pattern):
                raise PolicyViolation(
                    f"Acceso de {permission_type} bloqueado para "
                    f"'{relative_path}' por la regla '{pattern}'."
                )

        # La tool recibe el path absoluto después de ser validado.
        arguments["path"] = str(candidate)

        return arguments

    def _validate_command(self, command: str) -> None:
        """
        Comprueba que el comando no esté prohibido ni contenga
        operadores para encadenar otros comandos.
        """

        if not isinstance(command, str) or not command.strip():
            raise PolicyViolation(
                "El comando no puede estar vacío."
            )

        for operator in self.FORBIDDEN_SHELL_OPERATORS:
            if operator in command:
                raise PolicyViolation(
                    f"El operador de shell '{operator}' no está permitido."
                )

        denied_commands = (
            self.config
            .get("commands", {})
            .get("deny", [])
        )

        if self._contains_any(command, denied_commands):
            raise PolicyViolation(
                f"El comando '{command}' coincide con una regla prohibida."
            )

    @staticmethod
    def _contains_any(
        value: str,
        patterns: list[str],
    ) -> bool:
        lowered_value = value.lower()

        return any(
            pattern.lower() in lowered_value
            for pattern in patterns
        )

    @staticmethod
    def _matches_path(
        relative_path: str,
        pattern: str,
    ) -> bool:
        normalized_path = relative_path.replace("\\", "/")
        normalized_pattern = pattern.replace("\\", "/")

        # Elimina "./", pero conserva nombres que empiezan con punto,
        # como .env y .github.
        while normalized_pattern.startswith("./"):
            normalized_pattern = normalized_pattern[2:]

        # "**/" es redundante con la regla de abajo (un patrón sin "/"
        # ya matchea en cualquier profundidad), pero se acepta como
        # forma explícita -- ej. "**/*.pem".
        if normalized_pattern.startswith("**/"):
            normalized_pattern = normalized_pattern[3:]

        # Directorios como secrets/** o .github/** -- deben bloquear en
        # cualquier profundidad del árbol (ej. src/secrets/key.txt),
        # no solo si cuelgan directo de la raíz del workspace.
        if normalized_pattern.endswith("/**"):
            directory = normalized_pattern[:-3].rstrip("/")
            path_segments = normalized_path.split("/")

            return directory in path_segments

        # Patrones sin "/" (ej. ".env", "*.pem", "package-lock.json"):
        # igual que en un .gitignore, se comparan contra el nombre del
        # archivo nada más, así bloquean en cualquier profundidad y no
        # solo cuando el archivo está justo en la raíz del workspace.
        if "/" not in normalized_pattern:
            basename = normalized_path.rsplit("/", 1)[-1]
            return fnmatch(basename, normalized_pattern)

        # Patrones con path explícito (ej. "config/prod.yaml"):
        # anclados a la raíz del workspace.
        return fnmatch(
            normalized_path,
            normalized_pattern,
        )