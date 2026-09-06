"""Galería de imágenes generadas en la sesión."""
from __future__ import annotations

import streamlit as st

from src.bedrock.models import IMAGE_STYLES
from src.ui.state import galeria


def render() -> None:
    st.header("Galería")
    st.caption(
        "Todas las imágenes generadas en esta sesión, con su procedencia. "
        "La semilla permite reproducir cualquiera de ellas exactamente."
    )

    imagenes = galeria()
    if not imagenes:
        st.info(
            "La galería está vacía. Genera una imagen desde la pantalla "
            "**Generación de imágenes**.",
            icon="🖼️",
        )
        return

    columnas_filtro = st.columns([2, 2, 1])
    estilos_presentes = sorted({img.estilo.clave for img in imagenes})
    filtro_estilo = columnas_filtro[0].multiselect(
        "Filtrar por estilo",
        options=estilos_presentes,
        format_func=lambda k: IMAGE_STYLES[k].etiqueta,
    )
    filtro_autor = columnas_filtro[1].multiselect(
        "Filtrar por autor",
        options=sorted({img.autor for img in imagenes}),
    )
    columnas_filtro[2].metric("Total", len(imagenes))

    visibles = [
        img for img in imagenes
        if (not filtro_estilo or img.estilo.clave in filtro_estilo)
        and (not filtro_autor or img.autor in filtro_autor)
    ]

    if not visibles:
        st.warning("Ningún resultado con esos filtros.")
        return

    for fila_inicio in range(0, len(visibles), 3):
        fila = visibles[fila_inicio:fila_inicio + 3]
        columnas = st.columns(3)
        for columna, imagen in zip(columnas, fila):
            with columna, st.container(border=True):
                st.image(imagen.png_bytes, use_container_width=True)
                st.markdown(f"**{imagen.prompt_usuario[:70]}**")
                st.caption(
                    f"{imagen.estilo.etiqueta} · semilla `{imagen.seed}`\n\n"
                    f"{imagen.autor} · {imagen.momento_legible}"
                )
                st.download_button(
                    "Descargar",
                    data=imagen.png_bytes,
                    file_name=imagen.nombre_fichero,
                    mime="image/png",
                    key=f"dl_{imagen.id}_{fila_inicio}",
                    use_container_width=True,
                )
                with st.expander("Procedencia"):
                    for clave, valor in imagen.procedencia.items():
                        st.markdown(f"- **{clave}:** {valor}")
                    st.markdown("**Prompt completo enviado al modelo:**")
                    st.code(imagen.prompt_enviado, language="text")
