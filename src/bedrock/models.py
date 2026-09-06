"""Catálogo de modelos y perfiles de inferencia.

Este módulo es la traducción a código de la sección 3.3 de la memoria: qué
modelo se usa para cada tarea y con qué parámetros. Centralizarlo aquí evita
que los valores de temperatura queden dispersos por la interfaz y hace que la
justificación documental y el comportamiento real no puedan divergir.

Nota sobre la elección de familia de modelos
--------------------------------------------
Se emplean Claude Haiku 4.5 y Claude Sonnet 4.6 porque ambos exponen los
parámetros clásicos de muestreo (`temperature`, `top_p`), que son el objeto de
estudio de esta unidad. Los modelos más recientes de la familia Opus sustituyen
el muestreo explícito por razonamiento adaptativo y un parámetro de esfuerzo, y
rechazan `temperature`; adoptarlos habría hecho imposible demostrar el control
de inferencia que exige el caso práctico.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Identificadores de modelo en Amazon Bedrock
# ---------------------------------------------------------------------------

CLAUDE_FAST = "anthropic.claude-haiku-4-5"       # Tareas deterministas, alto volumen
CLAUDE_CREATIVE = "anthropic.claude-sonnet-4-6"  # Tareas creativas
STABLE_DIFFUSION = "stability.stable-diffusion-xl-v1"
TITAN_EMBEDDINGS = "amazon.titan-embed-text-v2:0"

ANTHROPIC_VERSION = "bedrock-2023-05-31"


class TextTask(str, Enum):
    """Operaciones de edición de contenido ofrecidas por la aplicación."""

    RESUMIR = "resumir"
    EXPANDIR = "expandir"
    CORREGIR = "corregir"
    VARIAR = "variar"

    @property
    def etiqueta(self) -> str:
        return {
            TextTask.RESUMIR: "Resumir",
            TextTask.EXPANDIR: "Expandir ideas",
            TextTask.CORREGIR: "Corregir gramática y estilo",
            TextTask.VARIAR: "Generar variaciones",
        }[self]


@dataclass(frozen=True)
class InferenceProfile:
    """Parámetros de inferencia de una tarea, con su justificación.

    El campo `justificacion` no es decorativo: alimenta la tabla de la memoria y
    el panel "Parámetros aplicados" de la interfaz, de modo que el usuario ve
    siempre por qué se está llamando al modelo de esa manera.
    """

    model_id: str
    temperature: float
    top_p: float
    max_tokens: int
    justificacion: str
    stop_sequences: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Perfiles por tarea de texto
#
# Regla aplicada: rigor y consistencia -> temperatura baja;
#                 creatividad y diversidad -> temperatura alta.
# ---------------------------------------------------------------------------

TEXT_PROFILES: dict[TextTask, InferenceProfile] = {
    TextTask.CORREGIR: InferenceProfile(
        model_id=CLAUDE_FAST,
        temperature=0.0,
        top_p=0.9,
        max_tokens=2048,
        justificacion=(
            "Corregir es una tarea de precisión: existe una respuesta correcta y "
            "no se busca invención. Temperatura 0.0 hace la salida prácticamente "
            "determinista, de modo que el mismo texto corregido dos veces produce "
            "el mismo resultado y el redactor puede confiar en la herramienta. Se "
            "usa el modelo más rápido y económico porque la tarea es de alto "
            "volumen y no requiere razonamiento profundo."
        ),
    ),
    TextTask.RESUMIR: InferenceProfile(
        model_id=CLAUDE_FAST,
        temperature=0.2,
        top_p=0.9,
        max_tokens=1024,
        justificacion=(
            "Resumir exige fidelidad al original: el riesgo real es la alucinación "
            "de datos que no estaban en el texto. Temperatura 0.2 conserva algo de "
            "naturalidad en la redacción sin abrir la puerta a que el modelo añada "
            "información. max_tokens se limita a 1024 porque un resumen más largo "
            "que eso ha dejado de ser un resumen."
        ),
    ),
    TextTask.EXPANDIR: InferenceProfile(
        model_id=CLAUDE_CREATIVE,
        temperature=0.7,
        top_p=0.95,
        max_tokens=4096,
        justificacion=(
            "Expandir requiere aportar desarrollo que no está en el original, así "
            "que se sube la temperatura a 0.7. Se cambia al modelo más capaz porque "
            "la calidad del desarrollo argumental es el valor de la operación. "
            "Top-P 0.95 amplía el abanico de continuaciones consideradas."
        ),
    ),
    TextTask.VARIAR: InferenceProfile(
        model_id=CLAUDE_CREATIVE,
        temperature=0.9,
        top_p=0.95,
        max_tokens=3072,
        justificacion=(
            "Generar variaciones es la única tarea donde la diversidad es el "
            "objetivo explícito: dos variaciones iguales son un fallo. Temperatura "
            "0.9 con Top-P 0.95 maximiza la dispersión de propuestas manteniéndolas "
            "coherentes. Es el punto más alto de la escala que usamos."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Estilos de imagen
#
# Cada estilo combina dos palancas: el `style_preset` nativo de SDXL y un
# sufijo de prompt. El preset por si solo no cubre todos los estilos que pide
# el caso (no existe un preset de pintura al oleo), de ahi la combinacion.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImageStyle:
    clave: str
    etiqueta: str
    style_preset: str
    prompt_suffix: str
    negative_prompt: str
    cfg_scale: float
    steps: int
    justificacion: str


IMAGE_STYLES: dict[str, ImageStyle] = {
    "realismo": ImageStyle(
        clave="realismo",
        etiqueta="Realismo fotográfico",
        style_preset="photographic",
        prompt_suffix=(
            "photorealistic, natural lighting, shallow depth of field, "
            "sharp focus, high detail, 50mm lens"
        ),
        negative_prompt=(
            "cartoon, illustration, painting, distorted anatomy, watermark, text"
        ),
        cfg_scale=7.0,
        steps=40,
        justificacion=(
            "CFG 7.0 es el equilibrio recomendado: adherencia al prompt sin los "
            "artefactos que aparecen por encima de 12. Se suben los pasos a 40 "
            "porque el realismo penaliza especialmente el ruido residual."
        ),
    ),
    "anime": ImageStyle(
        clave="anime",
        etiqueta="Anime / Manga",
        style_preset="anime",
        prompt_suffix=(
            "anime style, cel shading, clean line art, vibrant colors, "
            "expressive character design"
        ),
        negative_prompt=(
            "photorealistic, 3d render, blurry, watermark, text, extra limbs"
        ),
        cfg_scale=8.0,
        steps=30,
        justificacion=(
            "El preset nativo anime hace casi todo el trabajo. Se sube el CFG a "
            "8.0 porque el estilo se beneficia de una adherencia más estricta al "
            "prompt, y bastan 30 pasos: las superficies planas convergen antes."
        ),
    ),
    "oleo": ImageStyle(
        clave="oleo",
        etiqueta="Pintura al óleo",
        style_preset="digital-art",
        prompt_suffix=(
            "oil painting, thick impasto brushstrokes, visible canvas texture, "
            "rich pigment, classical composition, painterly"
        ),
        negative_prompt=(
            "photograph, digital render, smooth gradients, watermark, text"
        ),
        cfg_scale=6.5,
        steps=35,
        justificacion=(
            "SDXL no ofrece preset de óleo, así que el estilo se construye desde el "
            "prompt y se apoya en digital-art como base pictórica. Se baja el CFG "
            "a 6.5 a propósito: menos adherencia deja al modelo más libertad "
            "textural, que es justo lo que distingue una pintura de una foto."
        ),
    ),
    "ilustracion": ImageStyle(
        clave="ilustracion",
        etiqueta="Ilustración editorial",
        style_preset="line-art",
        prompt_suffix=(
            "editorial illustration, flat vector shapes, limited color palette, "
            "bold composition, generous negative space"
        ),
        negative_prompt=(
            "photorealistic, cluttered, gradient mesh, watermark, text"
        ),
        cfg_scale=7.5,
        steps=30,
        justificacion=(
            "Añadido sobre los tres estilos que pedía el enunciado porque es el "
            "registro más frecuente en campañas de marketing digital: composiciones "
            "planas que admiten superponer texto de campaña."
        ),
    ),
}

DEFAULT_STYLE = "realismo"

IMAGE_DEFAULTS = {
    "width": 1024,
    "height": 1024,
    "samples": 1,
}

# Perfil de embeddings para RAG
EMBEDDING_DIMENSIONS = 1024
