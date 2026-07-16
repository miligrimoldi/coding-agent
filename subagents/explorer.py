import json

from llm_client import get_client, MODEL
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from tools.loader import get_tools_for


ALLOWED_TOOLS = ["read_file", "list_files"]
EXPLORER_TOOLS = get_tools_for(ALLOWED_TOOLS)


class Explorer:
    MAX_ITERATIONS = 8
    REPEAT_THRESHOLD = 2

    SYSTEM_PROMPT = """
Sos el subagente Explorer dentro de un sistema multiagente de desarrollo
de código.

Tu única responsabilidad es entender el repositorio: su estructura de
carpetas, el lenguaje y framework utilizado, las dependencias principales,
las convenciones de organización del código y cuáles son los archivos
más relevantes para resolver el pedido del usuario.

Reglas:
- Usá list_files y read_file para inspeccionar el repositorio real.
- No inventes contenido que no hayas leído.
- No repitas la misma lectura o listado si ya obtuviste esa información.
- Prestá especial atención a package.json, schema.prisma, módulos,
  controllers, services, DTOs y tests.
- Cuando tengas suficiente evidencia, respondé con un único objeto JSON,
  sin texto alrededor, con esta forma:
  {
    "lenguaje": "...",
    "framework": "...",
    "archivos_relevantes": ["...", "..."],
    "estructura": "resumen breve de cómo está organizado el repositorio",
    "dependencias_detectadas": ["...", "..."],
    "scripts_detectados": {
      "build": "...",
      "test": "...",
      "lint": "..."
    },
    "puntos_de_entrada_sugeridos": [
      "archivo o función donde probablemente haya que implementar el cambio"
    ]
  }
"""

    def __init__(self, tool_executor: ToolExecutor):
        self.tool_executor = tool_executor

    def run(self, task_state: TaskState) -> SubagentResult:
        client = get_client()
        task_state.set_phase("exploration")

        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Pedido original del usuario: "
                    f"{task_state.original_request}"
                ),
            },
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
                task_state.record_iterations("explorer", iteration)

                return self._finalize(
                    task_state,
                    assistant_message.content,
                    iteration,
                )

            messages.append(assistant_message)

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name

                try:
                    tool_args = json.loads(
                        tool_call.function.arguments or "{}"
                    )
                except json.JSONDecodeError as exc:
                    tool_result = (
                        "Error: los argumentos de la tool no son JSON "
                        f"válido: {exc}"
                    )

                    task_state.record_observation(tool_result)

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_result,
                    })
                    continue

                if task_state.is_repeating(
                    subagent="explorer",
                    tool_name=tool_name,
                    args=tool_args,
                    threshold=self.REPEAT_THRESHOLD,
                ):
                    task_state.record_tool_call(
                        subagent="explorer",
                        tool_name=tool_name,
                        args=tool_args,
                        outcome="blocked_repeat",
                    )

                    task_state.record_observation(
                        f"Explorer repitió {tool_name}({tool_args})."
                    )

                    tool_result = (
                        "AVISO DEL SISTEMA: esta misma tool call ya fue "
                        "ejecutada dos veces. No la repitas. Usá otra "
                        "estrategia o entregá el JSON final."
                    )
                else:
                    tool_result = self.tool_executor.execute(
                        subagent="explorer",
                        tool_name=tool_name,
                        arguments=tool_args,
                        task_state=task_state,
                        allowed_tools=ALLOWED_TOOLS,
                    )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                })

        task_state.record_iterations(
            "explorer",
            self.MAX_ITERATIONS,
        )

        task_state.record_observation(
            f"Explorer alcanzó el límite de "
            f"{self.MAX_ITERATIONS} iteraciones."
        )

        return SubagentResult(
            subagent="explorer",
            summary=(
                "El Explorer no pudo concluir dentro del límite "
                "de iteraciones."
            ),
            data={},
            sources=["repository"],
        )

    @staticmethod
    def _finalize(
        task_state: TaskState,
        content: str,
        iterations: int,
    ) -> SubagentResult:
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            task_state.record_observation(
                "Explorer no devolvió JSON válido; "
                "se guardó como texto libre."
            )
            data = {"resumen_libre": content}

        return SubagentResult(
            subagent="explorer",
            summary=(
                f"Repositorio explorado en {iterations} iteraciones."
            ),
            data=data,
            sources=["repository"],
        )