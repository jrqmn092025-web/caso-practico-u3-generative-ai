"""Defensa frente a inyección de prompt (sección 3.6 de la memoria).

La delimitación por etiquetas solo funciona si el usuario no puede falsificar
las etiquetas. Este módulo cierra ese hueco y detecta los patrones de ataque
más frecuentes.

Modelo de amenaza asumido
-------------------------
El atacante es un usuario autenticado de la herramienta (un redactor, o alguien
que pega un texto de origen externo sin revisarlo). Su objetivo puede ser:
extraer el system prompt, hacer que el asistente ignore las reglas de marca, o
usar la herramienta para generar contenido fuera de política. No se asume un
atacante con acceso a la infraestructura: eso sería otro control.

Defensa en tres capas
---------------------
1. **Neutralización de delimitadores**: se impide cerrar el bloque <contenido>.
2. **Detección de patrones**: se avisa de frases con forma de instrucción.
3. **Prioridad declarada en el system prompt**: la instrucción explícita de que
   lo delimitado es dato. Vive en `src/prompts/system_prompts.py`.

Ninguna capa es suficiente por sí sola; la primera es la única determinista.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Patrones con forma de instrucción dirigida al modelo. La lista es
# deliberadamente conservadora: prefiere no marcar a marcar de más, porque un
# falso positivo sobre texto de marketing legítimo erosiona la confianza en la
# herramienta y acaba con el aviso desactivado.
_PATRONES_SOSPECHOSOS: list[tuple[str, str]] = [
    (r"ignora(?:r)?\s+(?:todas\s+)?(?:las\s+)?instrucciones?\s+(?:anteriores|previas)",
     "Intento de anular las instrucciones del sistema"),
    (r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?",
     "Intento de anular las instrucciones del sistema (inglés)"),
    (r"olvida\s+(?:todo\s+)?(?:lo\s+anterior|tus\s+instrucciones)",
     "Intento de anular las instrucciones del sistema"),
    (r"(?:revela|muestra|imprime|repite)\s+(?:tu|el)\s+(?:system\s+)?prompt",
     "Intento de extraer el prompt de sistema"),
    (r"(?:reveal|show|print|repeat)\s+(?:your|the)\s+(?:system\s+)?prompt",
     "Intento de extraer el prompt de sistema (inglés)"),
    (r"act[uú]a\s+como\s+(?:si\s+fueras\s+)?(?:otro|un)\s+", "Intento de suplantación de rol"),
    (r"you\s+are\s+now\s+", "Intento de suplantación de rol (inglés)"),
    (r"\bDAN\b|\bjailbreak\b|modo\s+desarrollador|developer\s+mode",
     "Patrón conocido de evasión de salvaguardas"),
    (r"</?\s*(?:system|instrucciones|instructions)\s*>",
     "Etiqueta de sistema falsificada en el contenido"),
    (r"nueva\s+instrucci[oó]n\s*:", "Instrucción embebida en el contenido"),
    (r"new\s+instructions?\s*:", "Instrucción embebida en el contenido (inglés)"),
]

# Delimitadores propios de la aplicación que el usuario no debe poder cerrar.
_DELIMITADORES_RESERVADOS = [
    ("</contenido>", "[/contenido]"),
    ("<contenido>", "[contenido]"),
    ("</guia_de_marca>", "[/guia_de_marca]"),
    ("<guia_de_marca>", "[guia_de_marca]"),
]


@dataclass
class GuardResult:
    """Resultado del saneamiento de una entrada."""

    texto_seguro: str
    delimitadores_neutralizados: int = 0
    alertas: list[str] = field(default_factory=list)

    @property
    def hay_sospecha(self) -> bool:
        return bool(self.alertas) or self.delimitadores_neutralizados > 0


def sanitize(texto: str) -> GuardResult:
    """Sanea el texto del usuario antes de incorporarlo al prompt.

    No rechaza la entrada: la neutraliza y avisa. Bloquear el texto sería la
    respuesta equivocada, porque un redactor puede legítimamente querer editar
    un artículo *sobre* inyección de prompt, y la herramienta debe permitirlo.
    Lo que no debe permitir es que ese texto cambie el comportamiento del
    modelo.
    """
    seguro = texto
    neutralizados = 0

    for original, reemplazo in _DELIMITADORES_RESERVADOS:
        ocurrencias = len(re.findall(re.escape(original), seguro, flags=re.IGNORECASE))
        if ocurrencias:
            seguro = re.sub(re.escape(original), reemplazo, seguro, flags=re.IGNORECASE)
            neutralizados += ocurrencias

    alertas: list[str] = []
    for patron, descripcion in _PATRONES_SOSPECHOSOS:
        if re.search(patron, seguro, flags=re.IGNORECASE):
            if descripcion not in alertas:
                alertas.append(descripcion)

    return GuardResult(
        texto_seguro=seguro,
        delimitadores_neutralizados=neutralizados,
        alertas=alertas,
    )
