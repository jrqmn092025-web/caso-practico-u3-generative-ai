"""Pantalla de colaboración: historial, comparación, comentarios y aprobación."""
from __future__ import annotations

import html

import streamlit as st

from src.domain.auth import USUARIOS, Permiso, Rol
from src.domain.versioning import EstadoPieza
from src.ui.components import barra_permiso, chip_estado
from src.ui.state import pieza_actual, usuario_actual


def _render_diff(pieza, desde: int, hasta: int) -> None:
    """Pinta la comparación entre dos versiones con marcas de color."""
    cambios = pieza.diff(desde, hasta)
    if not cambios:
        st.info("No hay diferencias entre estas versiones.")
        return

    piezas_html = []
    for marca, texto in cambios:
        seguro = html.escape(texto)
        if marca == "añadido":
            piezas_html.append(
                f'<span style="background:#D4F4DD;color:#12633A;'
                f'border-radius:3px;padding:1px 2px;">{seguro}</span>'
            )
        elif marca == "eliminado":
            piezas_html.append(
                f'<span style="background:#FBD9D7;color:#8C1D18;'
                f'text-decoration:line-through;border-radius:3px;'
                f'padding:1px 2px;">{seguro}</span>'
            )
        else:
            piezas_html.append(seguro)

    st.markdown(
        f'<div style="line-height:1.85;font-size:0.95rem;">{" ".join(piezas_html)}</div>',
        unsafe_allow_html=True,
    )

    stats = pieza.estadisticas_diff(desde, hasta)
    st.caption(
        f"**+{stats['añadidas']}** palabras añadidas · "
        f"**−{stats['eliminadas']}** eliminadas"
    )


def render() -> None:
    st.header("Colaboración")
    st.caption(
        "Historial de versiones, comparación de cambios, comentarios y ciclo de "
        "aprobación de la pieza."
    )

    usuario = usuario_actual()
    pieza = pieza_actual()

    cabecera = st.columns([3, 1])
    cabecera[0].subheader(pieza.titulo)
    cabecera[1].markdown(
        chip_estado(pieza.estado.etiqueta, pieza.estado.color),
        unsafe_allow_html=True,
    )

    tab_hist, tab_diff, tab_com, tab_equipo = st.tabs(
        ["Historial", "Comparar versiones", "Comentarios", "Equipo y permisos"]
    )

    # -- Historial ----------------------------------------------------------
    with tab_hist:
        st.caption(
            "Las versiones no se sobrescriben nunca. Restaurar apila una versión "
            "nueva, de modo que el registro de qué se aprobó y cuándo permanece "
            "íntegro."
        )
        for version in reversed(pieza.versiones):
            with st.container(border=True):
                columnas = st.columns([3, 2, 1])
                columnas[0].markdown(
                    f"**v{version.numero}** · {version.operacion}"
                )
                columnas[1].caption(
                    f"{version.autor} · {version.momento_legible}"
                )
                columnas[2].caption(version.resumen_parametros)

                st.markdown(
                    f"<div style='color:#4B5563;font-size:0.9rem;'>"
                    f"{html.escape(version.contenido[:280])}"
                    f"{'...' if len(version.contenido) > 280 else ''}</div>",
                    unsafe_allow_html=True,
                )
                if version.fuentes_rag:
                    st.caption("Guía de marca aplicada: " + " · ".join(version.fuentes_rag))

                if version.numero != len(pieza.versiones):
                    if usuario.puede(Permiso.RESTAURAR_VERSION):
                        if st.button(
                            f"Restaurar v{version.numero}",
                            key=f"restaurar_{version.numero}",
                        ):
                            nueva = pieza.restaurar(version.numero, usuario.nombre)
                            # Resincroniza el editor: si no, al volver a la
                            # pantalla de edicion seguiria el texto anterior.
                            st.session_state.editor_pendiente = nueva.contenido
                            st.success(
                                f"Restaurada v{version.numero} como "
                                f"v{len(pieza.versiones)}.",
                                icon="↩️",
                            )
                            st.rerun()
                    else:
                        st.caption(
                            "Solo el aprobador puede restaurar versiones."
                        )

    # -- Comparación --------------------------------------------------------
    with tab_diff:
        if len(pieza.versiones) < 2:
            st.info(
                "Hace falta al menos dos versiones para comparar. Edita el "
                "contenido y guarda el resultado."
            )
        else:
            numeros = [v.numero for v in pieza.versiones]
            columnas = st.columns(2)
            desde = columnas[0].selectbox(
                "Versión base", numeros, index=len(numeros) - 2,
                format_func=lambda n: f"v{n}",
            )
            hasta = columnas[1].selectbox(
                "Versión comparada", numeros, index=len(numeros) - 1,
                format_func=lambda n: f"v{n}",
            )
            st.divider()
            _render_diff(pieza, desde, hasta)

    # -- Comentarios --------------------------------------------------------
    with tab_com:
        if barra_permiso(usuario, Permiso.COMENTAR):
            with st.form("form_comentario", clear_on_submit=True):
                texto = st.text_area("Nuevo comentario", height=90)
                if st.form_submit_button("Publicar comentario", type="primary"):
                    if texto.strip():
                        pieza.comentar(usuario.nombre, usuario.rol.etiqueta, texto)
                        st.rerun()
                    else:
                        st.warning("El comentario está vacío.")

        st.divider()
        if not pieza.comentarios:
            st.caption("Todavía no hay comentarios en esta pieza.")
        for comentario in reversed(pieza.comentarios):
            with st.container(border=True):
                st.markdown(
                    f"**{comentario.autor}** · _{comentario.rol}_ · "
                    f"sobre v{comentario.version_numero} · "
                    f"{comentario.momento_legible}"
                )
                st.markdown(comentario.texto)

        st.divider()
        st.markdown("#### Ciclo de aprobación")
        if usuario.puede(Permiso.APROBAR):
            columnas = st.columns(3)
            if columnas[0].button("Aprobar pieza", type="primary"):
                pieza.estado = EstadoPieza.APROBADA
                pieza.comentar(usuario.nombre, usuario.rol.etiqueta, "Pieza aprobada.")
                st.rerun()
            if columnas[1].button("Devolver con cambios"):
                pieza.estado = EstadoPieza.RECHAZADA
                pieza.comentar(
                    usuario.nombre, usuario.rol.etiqueta,
                    "Pieza devuelta: requiere cambios.",
                )
                st.rerun()
            if columnas[2].button("Volver a borrador"):
                pieza.estado = EstadoPieza.BORRADOR
                st.rerun()
        else:
            st.info(
                "Solo el rol **Aprobador** cierra el ciclo. Esta separación de "
                "funciones evita que quien crea el contenido lo apruebe.",
                icon="🔒",
            )
            if st.button("Enviar a revisión"):
                pieza.estado = EstadoPieza.EN_REVISION
                pieza.comentar(
                    usuario.nombre, usuario.rol.etiqueta, "Enviada a revisión."
                )
                st.rerun()

    # -- Equipo -------------------------------------------------------------
    with tab_equipo:
        st.caption(
            "Matriz de permisos por rol. El diseño aplica separación de "
            "funciones: quien crea no aprueba."
        )
        for rol in Rol:
            with st.container(border=True):
                miembros = [u.nombre for u in USUARIOS if u.rol == rol]
                st.markdown(f"### {rol.etiqueta}")
                st.caption(rol.descripcion)
                st.markdown(f"**Miembros:** {', '.join(miembros)}")

                from src.domain.auth import PERMISOS_POR_ROL

                concedidos = PERMISOS_POR_ROL[rol]
                filas = [
                    f"| {p.descripcion} | {'✅' if p in concedidos else '—'} |"
                    for p in Permiso
                ]
                st.markdown(
                    "| Permiso | Concedido |\n|---|:--:|\n" + "\n".join(filas)
                )
