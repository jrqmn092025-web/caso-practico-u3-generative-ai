"""RAG sobre la guía de estilo de marca (sección 3.5 de la memoria).

Qué problema resuelve y por qué RAG y no memoria
-------------------------------------------------
La aplicación necesita que Claude conozca la guía de estilo interna: paleta,
terminología, prohibiciones legales. Ese conocimiento es **verificable, extenso
y cambiante**, y no puede ir en el system prompt por tres razones: ocuparía
miles de tokens en cada llamada, quedaría desactualizado cada vez que legal
cambie una norma, y no permitiría citar la fuente de una recomendación.

Eso es exactamente el caso de uso de RAG: recuperar de un corpus propio los
fragmentos relevantes para la consulta concreta y entregárselos al modelo antes
de responder.

**No es memoria.** La memoria conversacional (implementada en
`src/domain/versioning.py` y en el estado de sesión) aporta continuidad: qué
texto se está editando y qué versiones lleva. Son cosas distintas y resuelven
problemas distintos: RAG para el conocimiento, memoria para el contexto.

Arquitectura del índice
-----------------------
Índice vectorial en memoria, construido al arrancar:

    documentos .md -> troceado por secciones -> embeddings (Titan) -> matriz
    consulta -> embedding (Titan) -> similitud coseno -> top-k fragmentos

Se elige un índice en memoria y no una base vectorial gestionada (OpenSearch
Serverless, pgvector) porque el corpus son cuatro documentos de guía de estilo:
decenas de fragmentos, no millones. Introducir una base vectorial aquí sería
sobreingeniería. En la memoria se documenta el punto de corte a partir del cual
sí compensaría migrar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from src.bedrock.client import BedrockClient
from src.config import BRAND_GUIDE_DIR


# Umbral de similitud coseno por debajo del cual no se inyecta contexto.
#
# No es un número elegido a ojo. Se calibró midiendo la similitud del fragmento
# mejor puntuado en dos poblaciones de consultas: ocho consultas legítimas sobre
# la guía de marca y cuatro consultas de ruido ajenas al dominio (una receta de
# cocina, una duda de wifi, un resultado deportivo, un horario de trenes).
#
#   ruido      -> máximo 0.052
#   legítimas  -> mínimo 0.120
#
# 0.09 cae holgadamente en el hueco entre ambas, con margen a los dos lados. El
# script de calibración es `tests/test_rag_umbral.py`: si el corpus crece, dice
# en un segundo si la separación se mantiene.
UMBRAL_SIMILITUD = 0.09

# Cuántas veces se repite el título de sección en la representación indexable.
# Ver la nota sobre ponderación por campos en `Chunk`.
PESO_TITULO = 3


@dataclass(frozen=True)
class Chunk:
    """Fragmento indexable del corpus de marca.

    Se distinguen dos representaciones del mismo fragmento:

    - `texto`: lo que se inyecta en el prompt. Debe leerse bien.
    - `texto_indexable`: lo que se convierte en embedding. Puede estar sesgado
      hacia los campos con más señal.

    Separarlas permite aplicar *ponderación por campos*: el título de la sección
    describe su contenido mucho mejor que cualquier frase suelta del cuerpo, así
    que pesa más en el índice. Es la misma idea que BM25F o que los campos
    `title`/`body` de un buscador clásico. Sin esta separación habría que elegir
    entre un índice peor o un contexto con el título repetido tres veces.
    """

    documento: str
    seccion: str
    texto: str
    texto_indexable: str

    @property
    def cita(self) -> str:
        return f"{self.documento} › {self.seccion}"


@dataclass(frozen=True)
class Recuperacion:
    chunk: Chunk
    similitud: float


def trocear_documento(ruta: Path) -> list[Chunk]:
    """Trocea un documento Markdown por encabezados de segundo nivel.

    Se trocea por secciones semánticas en lugar de por ventana de N caracteres
    porque la guía de estilo ya viene estructurada por temas: partirla por
    longitud rompería tablas y separaría una prohibición de su contexto. El
    troceado debe respetar la estructura del documento cuando esta existe.
    """
    contenido = ruta.read_text(encoding="utf-8")
    titulo_doc = contenido.splitlines()[0].lstrip("# ").strip()

    partes = re.split(r"^##\s+", contenido, flags=re.MULTILINE)
    chunks: list[Chunk] = []

    for parte in partes[1:]:  # partes[0] es el preámbulo antes del primer ##
        lineas = parte.splitlines()
        seccion = lineas[0].strip()
        cuerpo = "\n".join(lineas[1:]).strip()
        if not cuerpo:
            continue

        texto = f"{titulo_doc} — {seccion}\n\n{cuerpo}"
        # Ponderación por campos: el título de la sección se repite en la
        # representación indexable para que pese más en el embedding, sin
        # ensuciar el texto que verá el modelo.
        indexable = "\n".join([seccion] * PESO_TITULO + [cuerpo])

        chunks.append(
            Chunk(
                documento=titulo_doc,
                seccion=seccion,
                texto=texto,
                texto_indexable=indexable,
            )
        )
    return chunks


class BrandKnowledgeBase:
    """Índice vectorial de la guía de estilo."""

    def __init__(self, client: BedrockClient, directorio: Path | None = None) -> None:
        self._client = client
        self._directorio = directorio or BRAND_GUIDE_DIR
        self._chunks: list[Chunk] = []
        self._matriz: np.ndarray | None = None
        self._tokens_indexado = 0

    # -- construcción -------------------------------------------------------

    def construir(self) -> None:
        """Indexa el corpus. Idempotente."""
        if self._matriz is not None:
            return

        chunks: list[Chunk] = []
        for ruta in sorted(self._directorio.glob("*.md")):
            chunks.extend(trocear_documento(ruta))

        if not chunks:
            self._chunks = []
            self._matriz = np.zeros((0, 0))
            return

        vectores = []
        for chunk in chunks:
            vector, trace = self._client.invoke_titan_embeddings(
                texto=chunk.texto_indexable
            )
            vectores.append(vector)
            self._tokens_indexado += trace.usage.get("inputTextTokenCount", 0)

        self._chunks = chunks
        self._matriz = np.array(vectores, dtype=np.float32)

    # -- consulta -----------------------------------------------------------

    def recuperar(self, consulta: str, k: int = 3,
                  umbral: float = UMBRAL_SIMILITUD) -> list[Recuperacion]:
        """Devuelve los k fragmentos más similares por coseno.

        El umbral evita el fallo más habitual de un RAG mal calibrado: entregar
        siempre k fragmentos aunque ninguno venga a cuento. Si la consulta no se
        parece a nada del corpus, es mejor no inyectar contexto que inyectar
        ruido, porque el ruido empuja al modelo a forzar conexiones inexistentes.
        """
        self.construir()
        if self._matriz is None or len(self._chunks) == 0:
            return []

        vector_consulta, _ = self._client.invoke_titan_embeddings(texto=consulta)
        q = np.array(vector_consulta, dtype=np.float32)

        # Los vectores llegan ya normalizados de Titan (normalize=True), pero se
        # renormaliza por seguridad: si el backend cambiara ese flag, el coseno
        # dejaría de ser correcto de forma silenciosa.
        q = q / (np.linalg.norm(q) or 1.0)
        matriz = self._matriz / (
            np.linalg.norm(self._matriz, axis=1, keepdims=True) + 1e-9
        )

        similitudes = matriz @ q
        indices = np.argsort(-similitudes)[:k]

        return [
            Recuperacion(chunk=self._chunks[i], similitud=float(similitudes[i]))
            for i in indices
            if similitudes[i] >= umbral
        ]

    def construir_contexto(self, consulta: str, k: int = 3) -> tuple[str, list[Recuperacion]]:
        """Recupera y formatea el contexto listo para el system prompt."""
        recuperados = self.recuperar(consulta, k=k)
        if not recuperados:
            return "", []

        bloques = [
            f"[Fuente: {r.chunk.cita}]\n{r.chunk.texto}" for r in recuperados
        ]
        return "\n\n---\n\n".join(bloques), recuperados

    # -- introspección para la interfaz -------------------------------------

    @property
    def num_chunks(self) -> int:
        return len(self._chunks)

    @property
    def documentos(self) -> list[str]:
        return sorted({c.documento for c in self._chunks})

    @property
    def tokens_indexado(self) -> int:
        return self._tokens_indexado


@lru_cache(maxsize=1)
def get_knowledge_base() -> BrandKnowledgeBase:
    """Índice compartido por toda la aplicación.

    Se cachea porque construirlo implica una llamada de embeddings por
    fragmento: rehacerlo en cada interacción de Streamlit multiplicaría el coste
    sin aportar nada, ya que el corpus no cambia durante la sesión.
    """
    kb = BrandKnowledgeBase(BedrockClient())
    kb.construir()
    return kb
