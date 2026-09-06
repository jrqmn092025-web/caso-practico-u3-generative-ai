"""Pantalla de generación de imágenes."""
from __future__ import annotations

import streamlit as st

from src.bedrock.client import BedrockError
from src.bedrock.models import IMAGE_STYLES
from src.domain.auth import Permiso
from src.services.text_service import ContenidoBloqueado
from src.ui.components import (
    avisos_seguridad,
    banner_backend,
    barra_permiso,
    panel_trazas,
)
from src.ui.state import añadir_a_galeria, get_image_service, usuario_actual


def render() -> None:
    st.header("Generación de imágenes")
    st.caption(
        "Describe la pieza visual, elige un estilo y genera. Cada imagen queda "
        "registrada con su prompt y su semilla para poder reproducirla."
    )
    banner_backend()

    usuario = usuario_actual()
    if not barra_permiso(usuario, Permiso.GENERAR_IMAGEN):
        return

    with st.form("form_imagen"):
        prompt = st.text_area(
            "Descripción de la imagen",
            value="Bodegón de bebidas frías sobre una mesa de terraza al atardecer",
            height=100,
            help=(
                "Describe la escena, la luz y el encaje. Evita nombres de marcas "
                "y de artistas: la política de la agencia los bloquea."
            ),
        )

        columnas = st.columns([2, 1, 1])
        estilo_clave = columnas[0].selectbox(
            "Estilo",
            options=list(IMAGE_STYLES.keys()),
            format_func=lambda k: IMAGE_STYLES[k].etiqueta,
        )
        fijar_semilla = columnas[1].checkbox(
            "Fijar semilla", value=True,
            help="Con la semilla fija, el mismo prompt produce la misma imagen.",
        )
        semilla = columnas[2].number_input(
            "Semilla", min_value=0, max_value=4_294_967_295, value=42,
            disabled=not fijar_semilla,
        )

        enviar = st.form_submit_button("Generar imagen", type="primary")

    estilo = IMAGE_STYLES[estilo_clave]
    with st.expander(f"Parámetros del estilo «{estilo.etiqueta}»", icon="🎛️"):
        columnas = st.columns(4)
        columnas[0].metric("style_preset", estilo.style_preset)
        columnas[1].metric("cfg_scale", estilo.cfg_scale)
        columnas[2].metric("steps", estilo.steps)
        columnas[3].metric("Resolución", "1024×1024")
        st.caption(estilo.justificacion)
        st.markdown("**Sufijo de prompt añadido:**")
        st.code(estilo.prompt_suffix, language="text")
        st.markdown("**Prompt negativo (peso −1.0):**")
        st.code(estilo.negative_prompt, language="text")

    if not enviar:
        return

    servicio = get_image_service()
    try:
        with st.spinner("Generando imagen..."):
            imagen = servicio.generar(
                prompt,
                estilo_clave=estilo_clave,
                seed=int(semilla) if fijar_semilla else None,
                autor=usuario.nombre,
            )
    except ContenidoBloqueado as exc:
        st.error(f"**Generación bloqueada.** {exc}", icon="🚫")
        return
    except BedrockError as exc:
        st.error(f"**Error de Bedrock.** {exc}", icon="💥")
        return

    añadir_a_galeria(imagen)
    st.success(f"Imagen generada con semilla `{imagen.seed}`.", icon="✅")
    avisos_seguridad([], 0, imagen.avisos_sesgo)

    columna_img, columna_meta = st.columns([3, 2])
    columna_img.image(imagen.png_bytes, use_container_width=True)

    with columna_meta:
        st.markdown("**Procedencia**")
        for clave, valor in imagen.procedencia.items():
            st.markdown(f"- **{clave}:** {valor}")
        st.download_button(
            "Descargar PNG",
            data=imagen.png_bytes,
            file_name=imagen.nombre_fichero,
            mime="image/png",
            use_container_width=True,
        )

    panel_trazas(imagen.trace)
