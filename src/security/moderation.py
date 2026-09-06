"""Moderación de entradas y salidas, y control de sesgo (sección 3.6).

Alcance y honestidad sobre sus límites
--------------------------------------
Esta es una moderación **por listas y reglas**, no un clasificador. Detecta lo
evidente y deja pasar lo sutil. En una implantación real sería la primera de
tres capas, no la única:

1. Esta capa: barata, determinista, ejecutada en el wrapper. Filtra lo obvio y
   documenta la política.
2. Amazon Bedrock Guardrails: políticas gestionadas de contenido, temas
   denegados y detección de información personal, aplicadas por AWS en la propia
   invocación.
3. Los filtros nativos de los modelos (Claude y Stable Diffusion traen los
   suyos, y SDXL devuelve `finishReason: CONTENT_FILTERED`).

Se declara así en la memoria porque presentar un filtro de listas como solución
completa sería el error de fondo que el propio caso práctico pide evitar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Severidad(str, Enum):
    BLOQUEO = "bloqueo"
    AVISO = "aviso"


@dataclass
class ModerationResult:
    permitido: bool
    motivos: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def mensaje(self) -> str:
        return " · ".join(self.motivos) if self.motivos else ""


# ---------------------------------------------------------------------------
# Categorías de bloqueo
# ---------------------------------------------------------------------------

_CATEGORIAS_BLOQUEO: list[tuple[str, str]] = [
    (r"\b(?:instrucciones?\s+para\s+)?(?:fabricar|construir|sintetizar)\s+"
     r"(?:un[ao]?\s+)?(?:bomba|explosivo|arma\s+biol[oó]gica|veneno)\b",
     "Contenido peligroso: instrucciones para causar daño físico"),
    (r"\b(?:child|menor(?:es)?)\s+(?:sexual|er[oó]tic)", "Contenido de explotación infantil"),
    (r"\bcontenido\s+sexual\s+expl[ií]cito\b|\bpornogr[aá]f",
     "Contenido sexual explícito: fuera de política para material de marca"),
    (r"\b(?:mata|matar|asesina|agrede)\s+a\s+(?:los|las|todos)\b",
     "Incitación a la violencia contra un grupo"),
]

# ---------------------------------------------------------------------------
# Marcas y personas reales: riesgo de derechos de imagen y de marca
# ---------------------------------------------------------------------------

_MARCAS_PROTEGIDAS = [
    "coca-cola", "cocacola", "pepsi", "nike", "adidas", "apple", "disney",
    "marvel", "pixar", "netflix", "starbucks", "ferrari", "rolex", "chanel",
    "louis vuitton", "gucci", "lego", "pokemon", "pokémon", "hello kitty",
]

_ESTILOS_DE_AUTOR = [
    "greg rutkowski", "artgerm", "banksy", "in the style of picasso",
    "estilo de picasso", "al estilo de dal[ií]", "estilo disney", "estilo pixar",
    "estilo ghibli", "studio ghibli",
]

# ---------------------------------------------------------------------------
# Sesgo: descriptores que fijan atributos personales sin necesidad funcional
# ---------------------------------------------------------------------------

_MARCADORES_SESGO = [
    (r"\b(?:un|una)\s+(?:enfermer[ao]|secretari[ao]|jefe|director[a]?|ingenier[ao]|"
     r"cient[ií]fic[ao]|program(?:ador|adora))\b(?!\s+(?:de|con|que))",
     "Rol profesional sin especificar diversidad: el modelo tenderá a reproducir "
     "el estereotipo dominante del conjunto de entrenamiento"),
    (r"\b(?:guap[ao]|atractiv[ao]|hermos[ao])\s+(?:mujer|chica|hombre|chico)\b",
     "Descriptor de atractivo asociado a género: riesgo de estereotipo"),
    (r"\b(?:ama\s+de\s+casa|hombre\s+de\s+negocios)\b",
     "Rol con carga de género histórica"),
]


def moderar_entrada(texto: str) -> ModerationResult:
    """Modera el texto que el usuario envía a cualquiera de los modelos."""
    motivos: list[str] = []
    avisos: list[str] = []
    bajo = texto.lower()

    for patron, motivo in _CATEGORIAS_BLOQUEO:
        if re.search(patron, bajo, flags=re.IGNORECASE):
            motivos.append(motivo)

    return ModerationResult(permitido=not motivos, motivos=motivos, avisos=avisos)


def moderar_prompt_imagen(prompt: str) -> ModerationResult:
    """Modera específicamente un prompt de generación de imagen.

    Añade a la moderación general dos controles propios del caso: marcas
    registradas y estilos de artistas identificables, que son el vector de
    riesgo de copyright más habitual en generación de imágenes para marketing.
    """
    resultado = moderar_entrada(prompt)
    motivos = list(resultado.motivos)
    avisos = list(resultado.avisos)
    bajo = prompt.lower()

    encontradas = [m for m in _MARCAS_PROTEGIDAS if m in bajo]
    if encontradas:
        motivos.append(
            "Marca registrada en el prompt (" + ", ".join(sorted(set(encontradas))) + "). "
            "Generar imágenes que evoquen marcas ajenas expone a la agencia a una "
            "reclamación por infracción."
        )

    estilos = [e for e in _ESTILOS_DE_AUTOR if re.search(e, bajo)]
    if estilos:
        motivos.append(
            "Estilo de artista o estudio identificable en el prompt. Imitar el "
            "estilo de un autor vivo o de un estudio con obra protegida es un "
            "riesgo legal y reputacional; describe el estilo por sus atributos "
            "visuales en lugar de por su autor."
        )

    for patron, aviso in _MARCADORES_SESGO:
        if re.search(patron, bajo, flags=re.IGNORECASE):
            if aviso not in avisos:
                avisos.append(aviso)

    return ModerationResult(permitido=not motivos, motivos=motivos, avisos=avisos)


def moderar_salida(texto: str) -> ModerationResult:
    """Revisa la salida del modelo antes de mostrarla.

    Filtrar solo la entrada es insuficiente: un prompt inocuo puede producir una
    salida problemática. Aquí se comprueba además que no se haya filtrado el
    prompt de sistema, que sería la señal de una inyección exitosa.
    """
    motivos: list[str] = []
    avisos: list[str] = []

    for patron, motivo in _CATEGORIAS_BLOQUEO:
        if re.search(patron, texto, flags=re.IGNORECASE):
            motivos.append(f"La respuesta generada contiene {motivo.lower()}")

    if re.search(r"REGLAS\s+INQUEBRANTABLES|PRIORIDAD\s+DE\s+INSTRUCCIONES", texto):
        motivos.append(
            "La respuesta parece contener el prompt de sistema: posible inyección "
            "de prompt con éxito. Se bloquea la salida."
        )

    for patron, aviso in _MARCADORES_SESGO:
        if re.search(patron, texto, flags=re.IGNORECASE):
            if aviso not in avisos:
                avisos.append(aviso)

    return ModerationResult(permitido=not motivos, motivos=motivos, avisos=avisos)
