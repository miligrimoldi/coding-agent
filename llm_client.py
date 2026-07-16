import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.environ.get("AGENT_MODEL", "gpt-5-nano")


def get_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENAI_API_KEY. Creá un archivo .env en la raíz del "
            "proyecto (podés copiar .env.example) con esa variable, o "
            "seteala manualmente con export OPENAI_API_KEY=... ."
        )
    return OpenAI(api_key=api_key)