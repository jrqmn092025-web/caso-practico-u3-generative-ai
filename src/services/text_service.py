"""Servicio de edición de contenido: orquesta seguridad, RAG y Claude.

Este módulo es la parte del *wrapper* que ejecuta la política de la aplicación.
El orden de los pasos no es arbitrario:

    1. Moderar la entrada        (barato; si se bloquea, no se gasta en el modelo)
    2. Sanear frente a inyección (neutraliza delimitadores antes de construir nada)
    3. Recuperar contexto RAG    (solo si el saneamiento salió limpio)
    4. Construir el prompt
    5. Invocar Claude
    6. Moderar la salida         (un prompt inocuo puede dar una salida que no lo es)

Moderar antes de llamar al modelo ahorra coste y latencia; moderar también
después es lo que convierte el control en algo real, porque el riesgo no está
solo en lo que el usuario escribe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.bedrock.client import BedrockClient, BedrockError, InvocationTrace
from src.bedrock.models import TEXT_PROFILES, InferenceProfile, TextTask
from src.prompts.system_prompts import build_system_prompt, build_user_message
from src.security.moderation import moderar_entrada, moderar_salida
from src.security.prompt_guard import sanitize
from src.services.rag_service import BrandKnowledgeBase, Recuperacion


class ContenidoBloqueado(RuntimeError):
    """La moderación impidió procesar o devolver el contenido."""


@dataclass
class ResultadoEdicion:
    texto: str
    tarea: TextTask
    profile: InferenceProfile
    trace: InvocationTrace
    system_prompt: str
    fuentes_rag: list[Recuperacion] = field(default_factory=list)
    alertas_seguridad: list[str] = field(default_factory=list)
    avisos_sesgo: list[str] = field(default_factory=list)
    delimitadores_neutralizados: int = 0

    @property
    def uso_rag(self) -> bool:
        return bool(self.fuentes_rag)


class TextService:
    def __init__(self, client: BedrockClient,
                 knowledge_base: BrandKnowledgeBase | None = None) -> None:
        self._client = client
        self._kb = knowledge_base

    def editar(self, texto: str, tarea: TextTask, *,
               usar_rag: bool = True) -> ResultadoEdicion:
        """Aplica una operación de edición sobre el texto.

        Raises:
            ContenidoBloqueado: si la moderación rechaza la entrada o la salida.
            BedrockError: si la invocación al modelo falla.
        """
        if not texto.strip():
            raise ContenidoBloqueado("No hay texto sobre el que trabajar.")

        # 1 - Moderación de entrada
        entrada = moderar_entrada(texto)
        if not entrada.permitido:
            raise ContenidoBloqueado(
                "La solicitud se ha bloqueado por política de contenido. "
                + entrada.mensaje
            )

        # 2 - Defensa frente a inyección de prompt
        guard = sanitize(texto)

        # 3 - Recuperación de contexto de marca
        fuentes: list[Recuperacion] = []
        contexto = ""
        if usar_rag and self._kb is not None:
            consulta = f"{tarea.etiqueta}. {guard.texto_seguro[:400]}"
            contexto, fuentes = self._kb.construir_contexto(consulta, k=3)

        # 4 - Construcción del prompt
        profile = TEXT_PROFILES[tarea]
        system_prompt = build_system_prompt(tarea, contexto_marca=contexto or None)
        user_content = build_user_message(guard.texto_seguro)

        # 5 - Invocación
        resultado = self._client.invoke_claude(
            system_prompt=system_prompt,
            user_content=user_content,
            profile=profile,
        )

        # 6 - Moderación de salida
        salida = moderar_salida(resultado.texto)
        if not salida.permitido:
            raise ContenidoBloqueado(
                "La respuesta generada se ha bloqueado antes de mostrarse. "
                + salida.mensaje
            )

        return ResultadoEdicion(
            texto=resultado.texto,
            tarea=tarea,
            profile=profile,
            trace=resultado.trace,
            system_prompt=system_prompt,
            fuentes_rag=fuentes,
            alertas_seguridad=guard.alertas,
            avisos_sesgo=salida.avisos,
            delimitadores_neutralizados=guard.delimitadores_neutralizados,
        )
