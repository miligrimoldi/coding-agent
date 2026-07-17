import json
from typing import Any

from llm_client import get_client, MODEL
from request_mode import detect_request_mode
from task_state import TaskState, SubagentResult
from tool_executor import ToolExecutor
from tools.loader import get_tools_for


ALLOWED_TOOLS = [
    "read_file",
    "list_files",
]

EXPLORER_TOOLS = get_tools_for(
    ALLOWED_TOOLS
)


class Explorer:
    MAX_ITERATIONS = 10
    REPEAT_THRESHOLD = 2

    SYSTEM_PROMPT = """
Sos el subagente Explorer dentro de un sistema multiagente de desarrollo
de código.

Tu responsabilidad es entender el repositorio real: estructura,
arquitectura, dependencias, convenciones, configuración, flujo actual y
archivos relevantes para el pedido del usuario.

Sos el principal responsable de inspeccionar el repositorio.

Recibís:
- pedido_original;
- task_mode, que puede ser description, analysis o implementation;
- memoria_previa_del_proyecto, que puede ser null.

Responsabilidades:
- Descubrir la estructura mediante list_files.
- Leer mediante read_file los archivos necesarios para comprender el flujo.
- Separar hechos comprobados de archivos solamente identificados.
- Producir evidencia del repositorio que puedan utilizar Researcher,
  Implementer y Reviewer.
- Para task_mode=description, producir una respuesta suficientemente clara
  como para que el pipeline pueda finalizar después del Explorer.

Reglas:
- Usá list_files y read_file para inspeccionar el repositorio real.
- Podés identificar un archivo como relevante si confirmaste su existencia
  mediante list_files.
- No describas el contenido de un archivo ni afirmes cómo funciona hasta
  haberlo leído con read_file.
- No inventes paths, contenido, dependencias, scripts ni configuraciones.
- No repitas una lectura o listado si ya obtuviste esa información.
- La memoria previa sirve únicamente como orientación. Confirmá en la
  ejecución actual los paths y hechos que uses en la respuesta final.
- No presentes como existente un archivo sugerido únicamente por la memoria.
- Si existe package.json, siempre debés leerlo antes de finalizar.
- No devuelvas scripts como "unknown" sin haber leído package.json.
- Prestá atención a controllers, services, DTOs, módulos, configuración de
  arranque, persistencia, schemas y tests relacionados con el pedido.
- Para pedidos de descripción, análisis o diagnóstico, reconstruí el flujo
  completo cuando sea posible: entrada, validación, controller, service,
  persistencia y tests.
- En archivos_relevantes incluí archivos concretos. Evitá carpetas genéricas
  o código generado, salvo que sean indispensables.
- Una afirmación de flujo_actual o configuraciones_verificadas debe incluir
  paths dentro de evidencia.
- Los paths usados como evidencia deben haber sido leídos con read_file.
- Cuando tengas evidencia suficiente, respondé con un único objeto JSON sin
  texto alrededor.

Formato:
{
  "task_mode": "description|analysis|implementation",
  "lenguaje": "...",
  "framework": "...",
  "resumen_para_usuario": "...",
  "archivos_leidos": [],
  "archivos_relevantes": [],
  "estructura": "...",
  "dependencias_detectadas": [],
  "scripts_detectados": {
    "build": "...",
    "test": "...",
    "lint": "..."
  },
  "flujo_actual": [
    {
      "descripcion": "...",
      "evidencia": ["path leído"]
    }
  ],
  "configuraciones_verificadas": [
    {
      "descripcion": "...",
      "evidencia": ["path leído"]
    }
  ],
  "aspectos_no_verificados": [],
  "puntos_de_entrada_sugeridos": []
}
"""

    FINAL_ITERATION_REMINDER = """
AVISO DEL SISTEMA: esta es la última iteración. Ya no podés usar tools.

Respondé únicamente con el objeto JSON final solicitado.

No afirmes hechos sobre archivos que no leíste. Incluí como no verificado
todo aquello que no hayas podido confirmar.
"""

    def __init__(
        self,
        tool_executor: ToolExecutor,
    ):
        self.tool_executor = tool_executor

    def run(
        self,
        task_state: TaskState,
    ) -> SubagentResult:
        client = get_client()

        task_state.set_phase(
            "exploration"
        )

        task_mode = detect_request_mode(
            task_state.original_request
        ).value

        memory = task_state.project_memory

        used_memory = bool(
            memory
            and memory.has_prior_knowledge()
        )

        user_content = {
            "pedido_original": (
                task_state.original_request
            ),
            "task_mode": task_mode,
            "memoria_previa_del_proyecto": (
                memory.as_context()
                if used_memory
                else None
            ),
        }

        messages = [
            {
                "role": "system",
                "content": self.SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    user_content,
                    ensure_ascii=False,
                ),
            },
        ]

        read_files_this_run: set[str] = set()

        for iteration in range(
            1,
            self.MAX_ITERATIONS + 1,
        ):
            is_last_iteration = (
                iteration
                == self.MAX_ITERATIONS
            )

            if is_last_iteration:
                messages.append({
                    "role": "user",
                    "content": (
                        self.FINAL_ITERATION_REMINDER
                    ),
                })

            response = (
                client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    tools=EXPLORER_TOOLS,
                    tool_choice=(
                        "none"
                        if is_last_iteration
                        else "auto"
                    ),
                )
            )

            assistant_message = (
                response.choices[0].message
            )

            if not assistant_message.tool_calls:
                task_state.record_iterations(
                    "explorer",
                    iteration,
                )

                return self._finalize(
                    task_state=task_state,
                    content=(
                        assistant_message.content
                    ),
                    iterations=iteration,
                    used_memory=used_memory,
                    task_mode=task_mode,
                    read_files_this_run=(
                        read_files_this_run
                    ),
                )

            messages.append(
                assistant_message
            )

            for tool_call in (
                assistant_message.tool_calls
            ):
                tool_name = (
                    tool_call.function.name
                )

                try:
                    tool_args = json.loads(
                        tool_call.function.arguments
                        or "{}"
                    )

                except json.JSONDecodeError as exc:
                    tool_result = (
                        "Error: los argumentos de la "
                        "tool no son JSON válido: "
                        f"{exc}"
                    )

                    task_state.record_observation(
                        tool_result
                    )

                    messages.append({
                        "role": "tool",
                        "tool_call_id": (
                            tool_call.id
                        ),
                        "content": tool_result,
                    })

                    continue

                if task_state.is_repeating(
                    subagent="explorer",
                    tool_name=tool_name,
                    args=tool_args,
                    threshold=(
                        self.REPEAT_THRESHOLD
                    ),
                ):
                    task_state.record_tool_call(
                        subagent="explorer",
                        tool_name=tool_name,
                        args=tool_args,
                        outcome="blocked_repeat",
                    )

                    task_state.record_observation(
                        "Explorer repitió "
                        f"{tool_name}({tool_args})."
                    )

                    tool_result = (
                        "AVISO DEL SISTEMA: esta misma "
                        "tool call ya fue ejecutada dos "
                        "veces. No la repitas. Usá otra "
                        "estrategia o entregá el JSON "
                        "final."
                    )

                else:
                    tool_result = (
                        self.tool_executor.execute(
                            subagent="explorer",
                            tool_name=tool_name,
                            arguments=tool_args,
                            task_state=task_state,
                            allowed_tools=ALLOWED_TOOLS,
                        )
                    )

                tool_result_text = str(
                    tool_result
                )

                tool_failed = bool(
                    tool_result_text.startswith(
                        "Error"
                    )
                    or tool_result_text.startswith(
                        "POLICY_BLOCKED"
                    )
                    or tool_result_text.startswith(
                        "TOOL_EXECUTION_ERROR"
                    )
                    or tool_result_text.startswith(
                        "AVISO DEL SISTEMA"
                    )
                )

                if (
                    tool_name == "read_file"
                    and not tool_failed
                ):
                    path = tool_args.get(
                        "path",
                        "",
                    )

                    if isinstance(path, str):
                        normalized_path = (
                            path.replace(
                                "\\",
                                "/",
                            )
                            .strip()
                            .strip("/")
                        )

                        if normalized_path:
                            read_files_this_run.add(
                                normalized_path
                            )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result_text,
                })

        task_state.record_iterations(
            "explorer",
            self.MAX_ITERATIONS,
        )

        task_state.record_observation(
            "Explorer alcanzó el límite de "
            f"{self.MAX_ITERATIONS} iteraciones."
        )

        return SubagentResult(
            subagent="explorer",
            summary=(
                "El Explorer no pudo concluir "
                "dentro del límite de iteraciones."
            ),
            data={
                "task_mode": task_mode,
                "archivos_leidos": sorted(
                    read_files_this_run
                ),
                "archivos_relevantes": [],
                "flujo_actual": [],
                "configuraciones_verificadas": [],
                "aspectos_no_verificados": [
                    "El Explorer alcanzó el límite "
                    "de iteraciones."
                ],
            },
            sources=(
                ["repository", "memory"]
                if used_memory
                else ["repository"]
            ),
        )

    @classmethod
    def _finalize(
        cls,
        *,
        task_state: TaskState,
        content: str | None,
        iterations: int,
        used_memory: bool,
        task_mode: str,
        read_files_this_run: set[str],
    ) -> SubagentResult:
        try:
            data = json.loads(
                content or ""
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            task_state.record_observation(
                "Explorer no devolvió JSON "
                "válido; se guardó como texto libre."
            )

            data = {
                "resumen_libre": content,
            }

        if not isinstance(data, dict):
            data = {
                "resumen_libre": content,
            }

        data["task_mode"] = task_mode

        # Esta lista no depende de lo que afirme el modelo:
        # se construye con las llamadas reales a read_file.
        data["archivos_leidos"] = sorted(
            read_files_this_run
        )

        aspectos_no_verificados = data.get(
            "aspectos_no_verificados",
            [],
        )

        if not isinstance(
            aspectos_no_verificados,
            list,
        ):
            aspectos_no_verificados = []

        data["flujo_actual"] = (
            cls._filter_verified_items(
                items=data.get(
                    "flujo_actual",
                    [],
                ),
                read_files=read_files_this_run,
                unverified=(
                    aspectos_no_verificados
                ),
            )
        )

        data["configuraciones_verificadas"] = (
            cls._filter_verified_items(
                items=data.get(
                    "configuraciones_verificadas",
                    [],
                ),
                read_files=read_files_this_run,
                unverified=(
                    aspectos_no_verificados
                ),
            )
        )

        data["aspectos_no_verificados"] = (
            aspectos_no_verificados
        )

        for field_name in (
            "archivos_relevantes",
            "dependencias_detectadas",
            "puntos_de_entrada_sugeridos",
        ):
            if not isinstance(
                data.get(field_name),
                list,
            ):
                data[field_name] = []

        if not isinstance(
            data.get("scripts_detectados"),
            dict,
        ):
            data["scripts_detectados"] = {}

        sources = (
            ["repository", "memory"]
            if used_memory
            else ["repository"]
        )

        return SubagentResult(
            subagent="explorer",
            summary=(
                "Repositorio explorado en "
                f"{iterations} iteraciones "
                f"({len(read_files_this_run)} "
                "archivo(s) leído(s))."
            ),
            data=data,
            sources=sources,
        )

    @staticmethod
    def _filter_verified_items(
        *,
        items: Any,
        read_files: set[str],
        unverified: list,
    ) -> list[dict]:
        """
        Conserva únicamente afirmaciones cuya evidencia contiene
        al menos un archivo realmente leído.
        """

        if not isinstance(items, list):
            return []

        verified_items: list[dict] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            description = (
                item.get("descripcion")
                or item.get("description")
                or ""
            )

            evidence = (
                item.get("evidencia")
                or item.get("evidence")
                or []
            )

            if not isinstance(evidence, list):
                evidence = []

            valid_evidence = [
                str(path)
                .replace("\\", "/")
                .strip()
                .strip("/")
                for path in evidence
                if (
                    isinstance(path, str)
                    and str(path)
                    .replace("\\", "/")
                    .strip()
                    .strip("/")
                    in read_files
                )
            ]

            if valid_evidence:
                normalized_item = dict(
                    item
                )

                normalized_item[
                    "evidencia"
                ] = valid_evidence

                normalized_item.pop(
                    "evidence",
                    None,
                )

                verified_items.append(
                    normalized_item
                )

            elif description:
                note = (
                    "No se pudo conservar como hecho "
                    "verificado: "
                    f"{description}"
                )

                if note not in unverified:
                    unverified.append(
                        note
                    )

        return verified_items