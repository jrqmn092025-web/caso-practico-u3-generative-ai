"""Aurora Studio — Generación de imágenes y edición de contenido con Amazon Bedrock.

Caso Práctico · Unidad 3 · Generative AI · Instituto Europeo de Posgrado
Autor: José Ruber Moncayo Navia

Punto de entrada de la aplicación Streamlit. Ejecutar con:

    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="Aurora Studio · IA generativa para marketing",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.config import ensure_runtime_dirs, get_settings  # noqa: E402
from src.domain.auth import USUARIOS  # noqa: E402
from src.ui import page_collab, page_editor, page_gallery, page_images  # noqa: E402
from src.ui.state import get_kb, init_state, pieza_actual  # noqa: E402

PAGINAS = {
    "Generación de imágenes": page_images.render,
    "Edición de contenido": page_editor.render,
    "Colaboración": page_collab.render,
    "Galería": page_gallery.render,
}


def sidebar() -> tuple[str, "st.delta_generator.DeltaGenerator"]:
    """Dibuja la barra lateral.

    Devuelve la página elegida y un marcador vacío para el bloque de estado.
    El bloque se rellena *después* de renderizar la página porque Streamlit
    ejecuta la barra lateral primero: si se pintara aquí, los contadores de
    galería y versiones mostrarían siempre el valor anterior a la acción que el
    usuario acaba de realizar.
    """
    settings = get_settings()

    with st.sidebar:
        st.title("Aurora Studio")
        st.caption("IA generativa para equipos creativos")

        pagina = st.radio("Navegación", list(PAGINAS.keys()), label_visibility="collapsed")

        st.divider()

        # -- Sesión de usuario ---------------------------------------------
        st.markdown("#### Sesión")
        indice = next(
            (i for i, u in enumerate(USUARIOS) if u.id == st.session_state.usuario_id),
            0,
        )
        seleccionado = st.selectbox(
            "Usuario",
            options=USUARIOS,
            index=indice,
            format_func=lambda u: f"{u.nombre} · {u.rol.etiqueta}",
        )
        st.session_state.usuario_id = seleccionado.id
        st.caption(seleccionado.rol.descripcion)

        st.divider()
        marcador_estado = st.empty()
        st.divider()
        st.caption(
            "Caso Práctico · Unidad 3 · Generative AI\n\n"
            "Instituto Europeo de Posgrado\n\n"
            "José Ruber Moncayo Navia"
        )

    return pagina, marcador_estado


def pintar_estado(marcador) -> None:
    """Rellena el bloque de estado con los valores ya actualizados."""
    settings = get_settings()
    pieza = pieza_actual()

    with marcador.container():
        st.markdown("#### Estado del sistema")
        if settings.is_mock:
            st.markdown("**Backend:** 🔌 Simulado (sin AWS)")
        else:
            st.markdown(f"**Backend:** ☁️ Bedrock · `{settings.aws_region}`")

        if settings.rag_enabled:
            kb = get_kb()
            st.markdown(
                f"**RAG:** ✅ activo · {kb.num_chunks} fragmentos "
                f"de {len(kb.documentos)} documentos"
            )
        else:
            st.markdown("**RAG:** ⛔ desactivado")

        st.markdown(
            f"**Pieza en curso:** v{len(pieza.versiones)} · {pieza.estado.etiqueta}"
        )
        n_img = len(st.session_state.galeria)
        st.markdown(
            f"**Galería:** {n_img} " + ("imagen" if n_img == 1 else "imágenes")
        )


def main() -> None:
    ensure_runtime_dirs()
    init_state()
    pagina, marcador_estado = sidebar()
    PAGINAS[pagina]()
    pintar_estado(marcador_estado)


if __name__ == "__main__":
    main()
