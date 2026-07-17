from enum import Enum


class RequestMode(str, Enum):
    DESCRIPTION = "description"
    ANALYSIS = "analysis"
    IMPLEMENTATION = "implementation"


READ_ONLY_MARKERS = (
    "sin modificar archivos",
    "sin modificar el código",
    "sin modificar el codigo",
    "sin hacer cambios",
    "sin cambiar archivos",
    "sin escribir archivos",
    "no modificar archivos",
    "no modifiques archivos",
    "no modificar el repositorio",
    "no modifiques el repositorio",
    "solo lectura",
)


IMPLEMENTATION_MARKERS = (
    "agregar ",
    "agregá ",
    "agrega ",
    "añadir ",
    "añadí ",
    "implementar ",
    "implementá ",
    "implementa ",
    "modificar ",
    "modificá ",
    "modifica ",
    "cambiar ",
    "cambiá ",
    "cambia ",
    "corregir ",
    "corregí ",
    "corrige ",
    "arreglar ",
    "arreglá ",
    "eliminar ",
    "eliminá ",
    "borrar ",
    "borrá ",
    "actualizar ",
    "actualizá ",
    "refactorizar ",
    "refactorizá ",
    "migrar ",
    "generar ",
    "escribir ",
    "crear un archivo",
    "crear una clase",
    "crear un endpoint",
    "crear tests",
    "crear pruebas",
)


ANALYSIS_MARKERS = (
    "analizar",
    "analizá",
    "evaluar",
    "evaluá",
    "revisar",
    "revisá",
    "auditar",
    "auditoría",
    "auditoria",
    "diagnóstico",
    "diagnostico",
    "detectar problemas",
    "identificar problemas",
    "identificar riesgos",
    "señalar riesgos",
    "posibles mejoras",
    "señalar mejoras",
    "sugerir mejoras",
    "recomendar mejoras",
    "recomendaciones",
)


DESCRIPTION_MARKERS = (
    "explicar",
    "explicá",
    "explicame",
    "explícame",
    "describir",
    "describí",
    "cómo funciona",
    "como funciona",
    "cómo está implementado",
    "como está implementado",
    "cómo está implementada",
    "como está implementada",
    "qué hace",
    "que hace",
    "mostrar la estructura",
    "describir la estructura",
    "entender el repositorio",
)


def detect_request_mode(
    request: str,
) -> RequestMode:
    """
    Clasifica la intención general del pedido.

    Prioridades:
    1. Una restricción explícita de no modificar evita cualquier
       ejecución de escritura.
    2. Un verbo de implementación indica que se esperan cambios.
    3. Un pedido de análisis requiere Explorer + Researcher.
    4. Un pedido meramente descriptivo puede terminar con Explorer.
    5. Ante dudas, se usa implementation para no omitir accidentalmente
       el pipeline de validación.
    """

    normalized = request.lower().strip()

    explicit_read_only = any(
        marker in normalized
        for marker in READ_ONLY_MARKERS
    )

    has_analysis_intent = any(
        marker in normalized
        for marker in ANALYSIS_MARKERS
    )

    has_description_intent = any(
        marker in normalized
        for marker in DESCRIPTION_MARKERS
    )

    has_implementation_intent = any(
        marker in normalized
        for marker in IMPLEMENTATION_MARKERS
    )

    if explicit_read_only:
        if has_analysis_intent:
            return RequestMode.ANALYSIS

        return RequestMode.DESCRIPTION

    if has_implementation_intent:
        return RequestMode.IMPLEMENTATION

    if has_analysis_intent:
        return RequestMode.ANALYSIS

    if has_description_intent:
        return RequestMode.DESCRIPTION

    return RequestMode.IMPLEMENTATION