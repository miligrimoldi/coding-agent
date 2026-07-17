import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

from dotenv import load_dotenv
from langfuse import get_client


# Obtiene la carpeta donde está observability.py.
# Se supone que el archivo .env también se encuentra en esa raíz.
PROJECT_ROOT = Path(__file__).resolve().parent

# Carga explícitamente las variables de entorno del proyecto.
load_dotenv(
    dotenv_path=PROJECT_ROOT / ".env"
)


class NoOpObservation:
    """
    Observación vacía utilizada cuando Langfuse no está configurado.

    Tiene el mismo método update() que una observación real, pero no hace
    nada. De esta manera, el resto del código puede usar observability.span()
    sin tener que comprobar constantemente si Langfuse está habilitado.
    """

    def update(self, **kwargs: Any) -> None:
        return None


class Observability:
    def __init__(self) -> None:
        # Langfuse solo se considera habilitado cuando están presentes
        # las tres variables necesarias para conectarse al proyecto.
        self.enabled = bool(
            os.getenv("LANGFUSE_PUBLIC_KEY")
            and os.getenv("LANGFUSE_SECRET_KEY")
            and os.getenv("LANGFUSE_BASE_URL")
        )

        # Obtiene el cliente global de Langfuse únicamente cuando
        # la configuración está completa.
        self.client = (
            get_client()
            if self.enabled
            else None
        )

    @contextmanager
    def span(
        self,
        *,
        name: str,
        input_data: Optional[Any] = None,
        metadata: Optional[
            Dict[str, Any]
        ] = None,
    ) -> Iterator[Any]:
        """
        Crea un span de Langfuse para observar una operación.

        Ejemplo:

            with observability.span(
                name="subagent.explorer",
                input_data={"request": user_request},
            ) as span:
                result = explorer.run(...)
                span.update(output=result)

        Si Langfuse no está configurado, devuelve una observación vacía
        para que el programa siga funcionando normalmente.
        """

        if not self.enabled or self.client is None:
            yield NoOpObservation()
            return

        # Crea el span y lo establece como observación actual.
        # Cualquier observación creada dentro de este bloque puede quedar
        # asociada jerárquicamente con este span.
        with self.client.start_as_current_observation(
            as_type="span",
            name=name,
            input=input_data,
            metadata=metadata or {},
        ) as observation:
            try:
                # Entrega la observación al bloque with que llamó a span().
                yield observation

            except Exception as exc:
                # Si ocurre un error dentro del bloque, se registra en
                # Langfuse antes de volver a propagar la excepción.
                observation.update(
                    level="ERROR",
                    status_message=str(exc),
                    output={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

                # El error no se oculta: vuelve al código que llamó al span.
                raise

    def flush(self) -> None:
        """
        Fuerza el envío de las observaciones pendientes a Langfuse.

        Conviene llamarlo antes de que termine el programa, especialmente
        porque este coding agent es un proceso de corta duración.
        """
        if self.enabled and self.client:
            self.client.flush()


# Se crea una única instancia compartida por todo el proyecto.
_observability = Observability()


def get_observability() -> Observability:
    """
    Devuelve la instancia global de observabilidad.

    Todos los módulos utilizan el mismo cliente y la misma configuración.
    """
    return _observability