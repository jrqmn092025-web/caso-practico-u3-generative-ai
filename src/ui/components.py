"""Componentes reutilizables de la interfaz."""
from __future__ import annotations

import json

import streamlit as st

from src.bedrock.client import InvocationTrace
from src.config import get_settings
from src.domain.auth import Permiso, Usuario
from src.services.rag_service import Recuperacion


def banner_backend() -> None:
    """Aviso permanente del modo de ejecución.

    Es una exigencia de honestidad, no un detalle de interfaz: quien vea una
    captura de esta aplicación debe poder saber de inmediato si el contenido
    procede de los modelos reales o de un sustituto.
    """
    settings = get_settings()
    if settings.is_mock:
        st.warning(
            "**Modo simulado.** Las respuestas no proceden de Amazon Bedrock: "
            "las genera un sustituto local que reproduce el contrato de la API. "
            "El código de integración es el real y se ejecuta íntegro hasta la "
            "frontera de red.",
            icon="🔌",
        )
    else:
        st.success(
            f"**Conectado a Amazon Bedrock** · región {settings.aws_region}",
            icon="☁️",
        )


def barra_permiso(usuario: Usuario, permiso: Permiso) -> bool:
    """Comprueba un permiso y explica la denegación si procede."""
    if usuario.puede(permiso):
        return True
    st.info(
        f"Tu rol actual (**{usuario.rol.etiqueta}**) no incluye el permiso "
        f"«{permiso.descripcion}». {usuario.rol.descripcion} "
        "Cambia de usuario en la barra lateral para probar este flujo.",
        icon="🔒",
    )
    return False


def panel_parametros(model_id: str, temperatura: float, top_p: float,
                     max_tokens: int, justificacion: str) -> None:
    """Muestra los parámetros aplicados y por qué.

    Exponer la justificación en la propia interfaz obliga a que el código y la
    memoria no puedan divergir: si mañana alguien cambia una temperatura sin
    revisar su razonamiento, la contradicción queda a la vista del usuario.
    """
    columnas = st.columns(4)
    columnas[0].metric("Modelo", model_id.split(".")[-1])
    columnas[1].metric("Temperatura", f"{temperatura}")
    columnas[2].metric("Top-P", f"{top_p}")
    columnas[3].metric("Máx. tokens", f"{max_tokens}")
    st.caption(justificacion)


def panel_trazas(trace: InvocationTrace, system_prompt: str | None = None) -> None:
    """Detalle técnico de la llamada: la evidencia de la integración."""
    with st.expander("Detalle técnico de la llamada a Bedrock", icon="🔍"):
        columnas = st.columns(3)
        columnas[0].metric("Latencia", f"{trace.latency_ms:.0f} ms")
        columnas[1].metric(
            "Tokens entrada", trace.usage.get("input_tokens", "—")
        )
        columnas[2].metric(
            "Tokens salida", trace.usage.get("output_tokens", "—")
        )

        st.markdown(
            f"**Operación:** `bedrock-runtime.invoke_model` · "
            f"**modelId:** `{trace.model_id}`"
        )
        st.markdown(
            "**Cuerpo de la petición** — este es el JSON exacto que se envía a "
            "Amazon Bedrock, idéntico en modo simulado y en modo real:"
        )
        st.code(trace.request_json, language="json")

        if system_prompt:
            st.markdown("**System prompt aplicado:**")
            st.code(system_prompt, language="text")


def panel_fuentes_rag(fuentes: list[Recuperacion]) -> None:
    """Fragmentos de la guía de marca inyectados en el prompt."""
    if not fuentes:
        st.caption(
            "Sin contexto de marca: ningún fragmento de la guía superó el "
            "umbral de similitud para esta consulta."
        )
        return

    with st.expander(
        f"Contexto de marca recuperado ({len(fuentes)} fragmentos)", icon="📚"
    ):
        st.caption(
            "Recuperado por similitud coseno sobre embeddings de Amazon Titan. "
            "Estos fragmentos se inyectan en el system prompt antes de llamar "
            "a Claude."
        )
        for fuente in fuentes:
            st.markdown(
                f"**{fuente.chunk.cita}** · similitud `{fuente.similitud:.3f}`"
            )
            st.caption(fuente.chunk.texto[:400] + "...")
            st.divider()


def avisos_seguridad(alertas: list[str], neutralizados: int,
                     avisos_sesgo: list[str]) -> None:
    """Resultado de los controles de seguridad de esta operación."""
    if neutralizados:
        st.warning(
            f"Se han neutralizado **{neutralizados}** delimitador(es) reservados "
            "en el texto de entrada. El contenido se ha procesado igualmente, "
            "pero no ha podido alterar las instrucciones del sistema.",
            icon="🛡️",
        )
    for alerta in alertas:
        st.warning(f"**Patrón sospechoso detectado:** {alerta}", icon="⚠️")
    for aviso in avisos_sesgo:
        st.info(f"**Revisión de sesgo:** {aviso}", icon="⚖️")


def chip_estado(etiqueta: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 10px;'
        f'border-radius:12px;font-size:0.78rem;font-weight:600;">{etiqueta}</span>'
    )
