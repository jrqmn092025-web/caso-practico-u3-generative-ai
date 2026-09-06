"""Pantalla de edición de contenido con Claude."""
from __future__ import annotations

import streamlit as st

from src.bedrock.client import BedrockError
from src.bedrock.models import TEXT_PROFILES, TextTask
from src.config import get_settings
from src.domain.auth import Permiso
from src.services.text_service import ContenidoBloqueado
from src.ui.components import (
    avisos_seguridad,
    banner_backend,
    barra_permiso,
    panel_fuentes_rag,
    panel_parametros,
    panel_trazas,
)
from src.ui.state import get_text_service, pieza_actual, usuario_actual


def render() -> None:
    st.header("Edición de contenido")
    st.caption(
        "Cada operación usa el modelo y los parámetros adecuados a su naturaleza, "
        "y queda registrada como una versión nueva de la pieza."
    )
    banner_backend()

    usuario = usuario_actual()
    pieza = pieza_actual()

    st.subheader(pieza.titulo)
    st.caption(
        f"Versión actual: **v{len(pieza.versiones)}** · "
        f"{len(pieza.contenido_actual.split())} palabras"
    )

    if not barra_permiso(usuario, Permiso.EDITAR_TEXTO):
        st.text_area(
            "Contenido actual (solo lectura)",
            value=pieza.contenido_actual,
            height=180,
            disabled=True,
        )
        return

    # El área de edición conserva lo que el usuario escriba entre
    # reejecuciones mediante una clave de sesión. Eso obliga a dos cosas:
    #
    # 1. Sembrar la clave la primera vez, porque Streamlit ignora `value` en
    #    cuanto la clave existe.
    # 2. Aplicar aquí —antes de crear el widget— cualquier cambio pendiente.
    #    Streamlit prohíbe escribir en la clave de un widget ya instanciado en
    #    la misma ejecución, así que guardar una versión no puede actualizar el
    #    editor directamente: deja el nuevo texto en `editor_pendiente` y es
    #    esta línea la que lo aplica en la ejecución siguiente.
    if "editor_pendiente" in st.session_state:
        st.session_state.editor_texto = st.session_state.pop("editor_pendiente")
    if "editor_texto" not in st.session_state:
        st.session_state.editor_texto = pieza.contenido_actual

    texto = st.text_area("Contenido a editar", height=180, key="editor_texto")

    settings = get_settings()
    columnas = st.columns([3, 2])
    with columnas[0]:
        etiquetas = {t: t.etiqueta for t in TextTask}
        tarea = st.radio(
            "Operación",
            options=list(TextTask),
            format_func=lambda t: etiquetas[t],
            horizontal=True,
        )
    with columnas[1]:
        usar_rag = st.toggle(
            "Aplicar guía de marca (RAG)",
            value=settings.rag_enabled,
            disabled=not settings.rag_enabled,
            help=(
                "Recupera de la guía de estilo los fragmentos relevantes y los "
                "inyecta en el system prompt antes de llamar a Claude."
            ),
        )

    profile = TEXT_PROFILES[tarea]
    panel_parametros(
        profile.model_id, profile.temperature, profile.top_p,
        profile.max_tokens, profile.justificacion,
    )

    if st.button(f"{tarea.etiqueta}", type="primary"):
        servicio = get_text_service()
        try:
            with st.spinner(
                f"{tarea.etiqueta} con {profile.model_id.split('.')[-1]}..."
            ):
                # El resultado se guarda en el estado de sesión, no en una
                # variable local. Streamlit reejecuta el script entero en cada
                # interacción, así que un resultado que solo viva en la pila
                # desaparece en cuanto el usuario pulsa cualquier otro botón, y
                # el de «Guardar como versión» nunca llegaría a ejecutarse.
                st.session_state.ultimo_resultado = servicio.editar(
                    texto, tarea, usar_rag=usar_rag
                )
        except ContenidoBloqueado as exc:
            st.session_state.ultimo_resultado = None
            st.error(f"**Operación bloqueada.** {exc}", icon="🚫")
            return
        except BedrockError as exc:
            st.session_state.ultimo_resultado = None
            st.error(f"**Error de Bedrock.** {exc}", icon="💥")
            return

    resultado = st.session_state.get("ultimo_resultado")
    if resultado is None:
        return

    st.divider()
    avisos_seguridad(
        resultado.alertas_seguridad,
        resultado.delimitadores_neutralizados,
        resultado.avisos_sesgo,
    )

    st.markdown(f"### Resultado · {resultado.tarea.etiqueta}")
    st.markdown(resultado.texto)

    columnas = st.columns([1, 1, 1, 2])
    if columnas[0].button("Guardar como versión", type="primary"):
        version = pieza.añadir_version(
            contenido=resultado.texto,
            autor=usuario.nombre,
            operacion=resultado.tarea.etiqueta,
            modelo=resultado.profile.model_id,
            temperatura=resultado.profile.temperature,
            fuentes_rag=[f.chunk.cita for f in resultado.fuentes_rag],
        )
        st.session_state.ultimo_resultado = None
        st.session_state.editor_pendiente = version.contenido
        st.success(f"Guardado como v{version.numero}.", icon="✅")
        st.rerun()

    columnas[1].download_button(
        "Descargar .txt",
        data=resultado.texto,
        file_name=f"{resultado.tarea.value}_v{len(pieza.versiones) + 1}.txt",
        mime="text/plain",
    )

    if columnas[2].button("Descartar"):
        st.session_state.ultimo_resultado = None
        st.rerun()

    panel_fuentes_rag(resultado.fuentes_rag)
    panel_trazas(resultado.trace, system_prompt=resultado.system_prompt)
