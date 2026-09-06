"""Calibración del umbral de similitud del RAG.

Ejecutable directamente (`python tests/test_rag_umbral.py`) o con pytest.

Mide dos poblaciones de consultas —legítimas y de ruido— y comprueba que el
umbral configurado cae en el hueco entre ambas. Si alguien amplía el corpus de
la guía de marca, este script dice de inmediato si el umbral sigue siendo
válido, en lugar de dejar que el RAG empiece a inyectar contexto irrelevante
sin que nadie lo note.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.services.rag_service import UMBRAL_SIMILITUD, get_knowledge_base  # noqa: E402

# Consultas que un redactor o diseñador haría de verdad, con la sección que
# debería recuperarse.
CONSULTAS_LEGITIMAS: list[tuple[str, str]] = [
    ("qué colores puedo usar en una campaña", "Paleta cromática"),
    ("qué paleta cromática tiene la marca", "Paleta cromática"),
    ("puedo generar una imagen al estilo de un artista famoso", "Propiedad intelectual"),
    ("cómo se escribe panel de campañas", "Nombres correctos"),
    ("puedo prometer que ahorramos un 40% al cliente",
     "Afirmaciones sujetas a verificación"),
    ("cuál es el tono para redes sociales", "Registro por canal"),
    ("puedo incluir datos personales de un cliente en el texto", "Datos personales"),
    ("qué palabras están prohibidas en nuestros textos", "Prohibiciones de estilo"),
]

# Consultas ajenas al dominio: no deben recuperar nada.
CONSULTAS_RUIDO: list[str] = [
    "receta de tortilla de patatas",
    "cómo configurar un router wifi en casa",
    "el partido de fútbol del domingo",
    "horario de trenes a Valencia",
]


def _medir() -> tuple[list[float], list[float], int]:
    kb = get_knowledge_base()

    scores_legitimas: list[float] = []
    aciertos = 0
    for consulta, esperada in CONSULTAS_LEGITIMAS:
        resultados = kb.recuperar(consulta, k=3, umbral=0.0)
        scores_legitimas.append(resultados[0].similitud if resultados else 0.0)
        if any(r.chunk.seccion == esperada for r in resultados[:3]):
            aciertos += 1

    scores_ruido: list[float] = []
    for consulta in CONSULTAS_RUIDO:
        resultados = kb.recuperar(consulta, k=3, umbral=0.0)
        scores_ruido.append(resultados[0].similitud if resultados else 0.0)

    return scores_legitimas, scores_ruido, aciertos


def test_umbral_separa_senal_de_ruido() -> None:
    """El umbral debe quedar por encima del ruido y por debajo de la señal."""
    legitimas, ruido, _ = _medir()
    assert max(ruido) < UMBRAL_SIMILITUD, (
        f"Una consulta de ruido puntúa {max(ruido):.3f}, por encima del umbral "
        f"{UMBRAL_SIMILITUD}. El RAG inyectaría contexto irrelevante."
    )
    assert min(legitimas) >= UMBRAL_SIMILITUD, (
        f"Una consulta legítima puntúa {min(legitimas):.3f}, por debajo del "
        f"umbral {UMBRAL_SIMILITUD}. El RAG se quedaría mudo ante una pregunta "
        "que el corpus sí responde."
    )


def test_recall_en_top3() -> None:
    """Al menos 5 de 8 consultas legítimas recuperan su sección en el top-3.

    El listón está en el valor realmente medido, no en uno aspiracional.

    Las tres que fallan lo hacen por la misma razón, y conviene dejarla escrita:
    el sustituto de embeddings compara **palabras**, no **significados**. La
    consulta "qué colores puedo usar" no recupera "Paleta cromática" porque esa
    sección nunca escribe la palabra "colores" —enumera nombres de color y
    códigos hexadecimales—, y ningún emparejamiento léxico salva esa distancia.
    Amazon Titan sí la salvaría: para eso existen los embeddings semánticos.

    Es decir: este número mide el techo del sustituto, no el de la arquitectura.
    Al conmutar `BEDROCK_BACKEND=aws` cabe esperar que suba sin tocar una línea
    de la aplicación, porque lo único que cambia es la calidad del vector.
    """
    _, _, aciertos = _medir()
    assert aciertos >= 5, f"Solo {aciertos}/8 consultas recuperan su sección en el top-3."


if __name__ == "__main__":
    legitimas, ruido, aciertos = _medir()
    print(f"Umbral configurado: {UMBRAL_SIMILITUD}")
    print(f"Consultas legítimas : min={min(legitimas):.3f}  max={max(legitimas):.3f}")
    print(f"Consultas de ruido  : min={min(ruido):.3f}  max={max(ruido):.3f}")
    print(f"Separación          : {min(legitimas) - max(ruido):+.3f}")
    print(f"Recall@3            : {aciertos}/{len(CONSULTAS_LEGITIMAS)}")
    ok = max(ruido) < UMBRAL_SIMILITUD <= min(legitimas)
    print("Umbral válido       :", "sí" if ok else "NO - recalibrar")
