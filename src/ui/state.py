"""Estado de sesión compartido por las pantallas.

Streamlit re-ejecuta el script completo en cada interacción, así que todo lo
que deba sobrevivir a un clic vive en `st.session_state`. Centralizar aquí su
creación evita el patrón disperso de `if "x" not in st.session_state` repetido
en cada pantalla, que es donde se cuelan los errores de inicialización.

Este estado es también la **memoria** de la aplicación en el sentido de la
sección 3.5: la pieza en curso, sus versiones y la galería de la sesión. Es
continuidad de trabajo, no conocimiento; el conocimiento lo aporta el RAG.
"""
from __future__ import annotations

import streamlit as st

from src.bedrock.client import BedrockClient
from src.config import get_settings
from src.domain.auth import USUARIOS, Usuario
from src.domain.versioning import Pieza, crear_pieza_ejemplo
from src.services.image_service import ImageService, ImagenGenerada
from src.services.rag_service import BrandKnowledgeBase, get_knowledge_base
from src.services.text_service import TextService


@st.cache_resource(show_spinner="Inicializando cliente de Bedrock...")
def get_client() -> BedrockClient:
    """Cliente compartido por toda la aplicación.

    `cache_resource` y no `cache_data`: es un objeto con conexión, no un valor
    serializable, y debe existir uno solo por proceso.
    """
    return BedrockClient()


@st.cache_resource(show_spinner="Indexando la guía de estilo de marca...")
def get_kb() -> BrandKnowledgeBase:
    return get_knowledge_base()


def get_text_service() -> TextService:
    settings = get_settings()
    kb = get_kb() if settings.rag_enabled else None
    return TextService(get_client(), kb)


def get_image_service() -> ImageService:
    return ImageService(get_client())


def init_state() -> None:
    """Crea el estado inicial. Idempotente."""
    if "usuario_id" not in st.session_state:
        st.session_state.usuario_id = USUARIOS[1].id  # arranca como redactor
    if "pieza" not in st.session_state:
        st.session_state.pieza = crear_pieza_ejemplo()
    if "galeria" not in st.session_state:
        st.session_state.galeria = []
    if "ultimo_resultado" not in st.session_state:
        st.session_state.ultimo_resultado = None
    if "pagina" not in st.session_state:
        st.session_state.pagina = "Generación de imágenes"


def usuario_actual() -> Usuario:
    from src.domain.auth import get_usuario

    return get_usuario(st.session_state.usuario_id)


def pieza_actual() -> Pieza:
    return st.session_state.pieza


def galeria() -> list[ImagenGenerada]:
    return st.session_state.galeria


def añadir_a_galeria(imagen: ImagenGenerada) -> None:
    # Las más recientes primero: es el orden en que el diseñador quiere verlas.
    st.session_state.galeria.insert(0, imagen)
