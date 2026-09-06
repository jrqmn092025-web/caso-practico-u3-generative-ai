"""Genera el diagrama de arquitectura de la sección 3.2.

Se dibuja con matplotlib en lugar de con una herramienta externa para que el
diagrama sea reproducible: forma parte del repositorio y se regenera con un
comando, en lugar de ser una imagen suelta que nadie sabe de dónde salió.

    python scripts/generar_diagrama.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import ASSETS_DIR  # noqa: E402

# Paleta de la guía de marca del propio caso.
AZUL = "#1B3A5C"
CORAL = "#F0554F"
AMBAR = "#F7C948"
GRAFITO = "#23282D"
HUESO = "#F5F3EE"
VERDE = "#2E9E5B"
GRIS = "#8A9099"
GRIS_CLARO = "#B9BFC7"

# Retícula horizontal: todas las filas ocupan el mismo ancho útil.
X0, ANCHO_UTIL, HUECO = 0.05, 0.86, 0.028
PAD = 0.005  # padding del boxstyle; hay que descontarlo del hueco visual


def columnas(n: int) -> list[tuple[float, float]]:
    """Devuelve (x, ancho) de n columnas repartidas en el ancho útil."""
    w = (ANCHO_UTIL - (n - 1) * HUECO) / n
    return [(X0 + i * (w + HUECO), w) for i in range(n)]


def caja(ax, x, y, w, h, titulo, subtitulo="", color=AZUL,
         texto_color="white", discontinua=False):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle=f"round,pad={PAD},rounding_size=0.018",
            facecolor=color,
            edgecolor=GRIS if discontinua else color,
            linewidth=1.6 if discontinua else 1.2,
            linestyle=(0, (5, 3)) if discontinua else "-",
            zorder=3,
        )
    )
    ax.text(
        x + w / 2, y + h / 2 + (0.014 if subtitulo else 0),
        titulo, ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=texto_color, zorder=4,
    )
    if subtitulo:
        ax.text(
            x + w / 2, y + h / 2 - 0.026,
            subtitulo, ha="center", va="center",
            fontsize=8, color=texto_color, alpha=0.92, zorder=4,
        )


def etiqueta_capa(ax, y, texto):
    """Rotula una capa.

    Lleva un recuadro blanco opaco porque algunas flechas verticales pasan por
    esta banda; sin el recuadro, la linea atraviesa el texto y lo hace ilegible.
    """
    ax.text(X0, y, texto, fontsize=8, fontweight="bold",
            color=GRIS, va="center", zorder=6,
            bbox=dict(facecolor="white", edgecolor="none", pad=2.5))


def flecha(ax, x, y_desde, y_hasta, color=GRAFITO, lw=1.6, discontinua=False):
    ax.add_patch(
        FancyArrowPatch(
            (x, y_desde), (x, y_hasta),
            arrowstyle="-|>", mutation_scale=13,
            linewidth=lw, color=color,
            linestyle=(0, (4, 3)) if discontinua else "-",
            zorder=2,
        )
    )


def construir() -> Path:
    fig, ax = plt.subplots(figsize=(13.2, 9.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(0.5, 0.975, "Aurora Studio · Arquitectura del sistema",
            ha="center", fontsize=16, fontweight="bold", color=GRAFITO)
    ax.text(0.5, 0.947,
            "Generación de imágenes y edición de contenido sobre Amazon Bedrock",
            ha="center", fontsize=10, color=GRIS)

    # ------------------------------------------------------- CAPA 1 · UI
    etiqueta_capa(ax, 0.907, "INTERFAZ DE USUARIO  ·  Streamlit")
    cols4 = columnas(4)
    ui = [
        ("Generación", "imágenes · estilos"),
        ("Edición", "4 operaciones"),
        ("Colaboración", "versiones · comentarios"),
        ("Galería", "catálogo · descarga"),
    ]
    for (x, w), (titulo, sub) in zip(cols4, ui):
        caja(ax, x, 0.815, w, 0.072, titulo, sub, AZUL)

    for x, w in cols4:
        flecha(ax, x + w / 2, 0.815, 0.762, color=GRIS_CLARO, lw=1.4)

    # -------------------------------------------------- CAPA 2 · WRAPPER
    etiqueta_capa(ax, 0.782, "WRAPPER  ·  orquestación, política y estado")
    ax.add_patch(
        FancyBboxPatch(
            (X0 - 0.014, 0.505), ANCHO_UTIL + 0.028, 0.245,
            boxstyle="round,pad=0.004,rounding_size=0.016",
            facecolor=HUESO, edgecolor=AMBAR, linewidth=2, zorder=1,
        )
    )

    politica = [
        ("Moderación", "entrada y salida", CORAL, "white"),
        ("Prompt guard", "anti-inyección", CORAL, "white"),
        ("System prompts", "4 pilares", AMBAR, GRAFITO),
        ("RAG", "guía de marca", VERDE, "white"),
    ]
    for (x, w), (titulo, sub, color, tc) in zip(cols4, politica):
        caja(ax, x, 0.638, w, 0.072, titulo, sub, color, tc)

    cols3 = columnas(3)
    servicios = [
        ("Servicio de texto", "perfiles de inferencia por tarea"),
        ("Servicio de imagen", "estilos · semilla · procedencia"),
        ("Dominio", "roles · versiones · comentarios"),
    ]
    for (x, w), (titulo, sub) in zip(cols3, servicios):
        caja(ax, x, 0.528, w, 0.072, titulo, sub, GRAFITO)

    # ----------------------------------------------- CAPA 3 · TRANSPORTE
    etiqueta_capa(ax, 0.478, "TRANSPORTE  ·  única línea de corte del sistema")
    cols2 = columnas(2)
    flecha(ax, cols2[0][0] + cols2[0][1] / 2, 0.505, 0.452)
    flecha(ax, cols2[1][0] + cols2[1][1] / 2, 0.505, 0.452,
           color=GRIS, discontinua=True)

    caja(ax, cols2[0][0], 0.372, cols2[0][1],
         0.072, "Cliente bedrock-runtime (boto3)",
         "invoke_model(modelId, body)", AZUL)
    caja(ax, cols2[1][0], 0.372, cols2[1][1], 0.072,
         "MockBedrockRuntime", "mismo contrato · valida los payloads",
         GRIS, discontinua=True)

    # Conmutador entre ambos backends, en el hueco central.
    x_centro = cols2[0][0] + cols2[0][1] + HUECO / 2
    ax.text(x_centro, 0.408, "⇄", ha="center", va="center",
            fontsize=17, color=CORAL, fontweight="bold", zorder=5)
    ax.text(x_centro, 0.352, "BEDROCK_BACKEND", ha="center", va="center",
            fontsize=7, color=CORAL, fontweight="bold", zorder=5)

    # -------------------------------------------------- CAPA 4 · BEDROCK
    etiqueta_capa(ax, 0.322, "AMAZON BEDROCK  ·  modelos fundacionales")
    flecha(ax, cols2[0][0] + cols2[0][1] / 2, 0.372, 0.296)
    flecha(ax, cols2[1][0] + cols2[1][1] / 2, 0.372, 0.296,
           color=GRIS, discontinua=True)

    modelos = [
        ("Claude", "haiku-4-5 · sonnet-4-6", "#7C5CE0"),
        ("Stable Diffusion XL", "texto → imagen", "#0E8FD0"),
        ("Titan Embeddings", "vectores para RAG", "#12A594"),
    ]
    for (x, w), (titulo, sub, color) in zip(cols3, modelos):
        caja(ax, x, 0.216, w, 0.072, titulo, sub, color)

    # --------------------------------------------- CAPA 5 · ALMACENAMIENTO
    etiqueta_capa(ax, 0.166, "ALMACENAMIENTO")
    for x, w in cols3:
        flecha(ax, x + w / 2, 0.216, 0.140, color=GRIS_CLARO, lw=1.4)

    almacen = [
        ("Galería de imágenes", "PNG + procedencia"),
        ("Historial de versiones", "registro solo-anexado"),
        ("Índice vectorial", "guía de marca · en memoria"),
    ]
    for (x, w), (titulo, sub) in zip(cols3, almacen):
        caja(ax, x, 0.060, w, 0.072, titulo, sub, "#E4E7EB", GRAFITO)

    # ------------------------------------------------------------ LEYENDA
    leyenda = [
        mpatches.Patch(color=CORAL, label="Controles de seguridad"),
        mpatches.Patch(color=AMBAR, label="Instrucciones del modelo"),
        mpatches.Patch(color=VERDE, label="Conocimiento externo (RAG)"),
        mpatches.Patch(color=GRIS, label="Sustituto de transporte (modo mock)"),
    ]
    ax.legend(
        handles=leyenda, loc="upper center", bbox_to_anchor=(0.5, 0.045),
        ncol=4, frameon=False, fontsize=8.5,
    )

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    destino = ASSETS_DIR / "arquitectura.png"
    fig.savefig(destino, dpi=190, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return destino


if __name__ == "__main__":
    ruta = construir()
    print(f"Diagrama generado: {ruta}")
