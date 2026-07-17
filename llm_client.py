import os
from pathlib import Path

from dotenv import load_dotenv
from langfuse.openai import OpenAI


# Ruta de la raíz del proyecto, donde está este archivo.
PROJECT_ROOT = Path(__file__).resolve().parent

# Carga explícitamente el .env de la raíz.
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")


MODEL = os.getenv(
    "AGENT_MODEL",
    "gpt-5-nano",
)


def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Falta OPENAI_API_KEY. Creá un archivo .env en la raíz "
            "del proyecto o configurá la variable manualmente."
        )

    return OpenAI(
        api_key=api_key,
        timeout=90.0,
        max_retries=1,
    )