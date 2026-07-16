import json

from llm_client import get_client, MODEL
from tools.loader import get_tools_for, get_implementations_for
from task_state import TaskState, SubagentResult

ALLOWED_TOOLS = ["read_file", "list_files"]

EXPLORER_TOOLS = get_tools_for(ALLOWED_TOOLS)
EXPLORER_TOOL_IMPL = get_implementations_for(ALLOWED_TOOLS)


class Explorer:
    MAX_ITERATIONS = 8
    REPEAT_THRESHOLD = 2  # a la 2da vez que se repite la misma tool call, se corta

    SYSTEM_PROMPT = """
Sos el subagente Explorer dentro de un sistema multiagente de desarrollo
de codigo (el sistema completo puede agregar funcionalidades a un
proyecto existente, no solo analizarlo).

Tu unica responsabilidad es entender el repositorio: su estructura de
carpetas, el lenguaje/framework utilizado, las dependencias principales,
las convenciones de organizacion del codigo, y cuales son los archivos
mas relevantes -- en particular, los que el Implementer probablemente
necesite tocar o mirar como referencia para agregar la funcionalidad
pedida por el usuario.

Reglas:
- Usa list_files y read_file para inspeccionar el repositorio real. No
  inventes contenido que no hayas leido.
- No repitas la misma lectura o listado si ya obtuviste esa informacion.
- Cuando tengas suficiente evidencia, respondé con tu conclusion final
  en un unico bloque JSON (sin texto alrededor) con esta forma exacta:
  {
    "lenguaje": "...",
    "framework": "...",
    "archivos_relevantes": ["...", "..."],
    "estructura": "resumen breve de como esta organizado el repo",
    "dependencias_detectadas": ["...", "..."],
    "puntos_de_entrada_sugeridos": ["archivo o funcion donde probablemente haya que agregar la funcionalidad pedida"]
  }
"""

    def run(self, task_state: TaskState) -> SubagentResult:
        client = get_client()

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Pedido original del usuario: {task_state.original_request}"},
        ]

        for iteration in range(1, self.MAX_ITERATIONS + 1):
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=EXPLORER_TOOLS,
                tool_choice="auto",
            )
            assistant_message = response.choices[0].message

            if not assistant_message.tool_calls:
                return self._finalize(task_state, assistant_message.content, iteration)

            messages.append(assistant_message)

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments or "{}")

                if task_state.is_repeating(tool_name, tool_args, threshold=self.REPEAT_THRESHOLD):
                    task_state.record_observation(
                        f"Explorer repitio {tool_name}({tool_args}) mas de "
                        f"{self.REPEAT_THRESHOLD} veces -- se corto la ejecucion."
                    )
                    tool_result = (
                        "AVISO DEL SISTEMA: ya llamaste a esta tool con estos "
                        "mismos argumentos antes y no aporto informacion nueva. "
                        "No la repitas. Si ya tenes suficiente evidencia, "
                        "respondé ahora con el JSON final. Si no, probá con "
                        "un path o argumento distinto."
                    )
                else:
                    task_state.record_tool_call(tool_name, tool_args)
                    tool_result = self._run_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

        task_state.record_observation(
            f"Explorer alcanzo el limite de {self.MAX_ITERATIONS} iteraciones sin concluir."
        )
        return SubagentResult(
            subagent="explorer",
            summary="El Explorer no pudo concluir dentro del limite de iteraciones.",
            data={},
            sources=["repo"],
        )

    @staticmethod
    def _run_tool(name: str, args: dict) -> str:
        if name not in EXPLORER_TOOL_IMPL:
            return f"Error: el Explorer no tiene permitido usar la tool '{name}'."
        return EXPLORER_TOOL_IMPL[name](**args)

    @staticmethod
    def _finalize(task_state: TaskState, content: str, iterations: int) -> SubagentResult:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            task_state.record_observation(
                "Explorer no devolvio JSON valido en su respuesta final; "
                "se guarda como texto libre."
            )
            data = {"resumen_libre": content}

        return SubagentResult(
            subagent="explorer",
            summary=f"Repositorio explorado en {iterations} iteraciones.",
            data=data,
            sources=["repo"],
        )