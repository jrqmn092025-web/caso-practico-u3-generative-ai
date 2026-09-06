"""Historial de versiones y comentarios de las piezas creativas.

Este módulo implementa la **memoria** de la aplicación, en el sentido preciso
que exige la sección 3.5: continuidad del trabajo en curso. No es RAG, y la
distinción importa:

- El historial sabe *qué se está editando y por dónde va*. Es estado de la
  sesión de trabajo.
- El RAG sabe *qué dice la guía de marca*. Es conocimiento externo verificable.

Decisión de diseño: las versiones no se sobrescriben nunca
-----------------------------------------------------------
Cada operación apila una versión nueva y conserva la anterior. Restaurar no
borra: apila una versión más cuyo contenido es el de la versión restaurada. El
historial es, por tanto, un registro de solo-anexado.

Es más caro en memoria y es lo correcto: en un flujo de aprobación, poder
demostrar qué se aprobó y cuándo es un requisito de trazabilidad, no una
comodidad. Un `undo` destructivo haría imposible auditar una pieza publicada.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.bedrock.models import TextTask


class EstadoPieza(str, Enum):
    BORRADOR = "borrador"
    EN_REVISION = "en_revision"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"

    @property
    def etiqueta(self) -> str:
        return {
            EstadoPieza.BORRADOR: "Borrador",
            EstadoPieza.EN_REVISION: "En revisión",
            EstadoPieza.APROBADA: "Aprobada",
            EstadoPieza.RECHAZADA: "Devuelta",
        }[self]

    @property
    def color(self) -> str:
        return {
            EstadoPieza.BORRADOR: "#6B7280",
            EstadoPieza.EN_REVISION: "#F7C948",
            EstadoPieza.APROBADA: "#2E9E5B",
            EstadoPieza.RECHAZADA: "#F0554F",
        }[self]


@dataclass(frozen=True)
class Version:
    """Una instantánea del texto de una pieza."""

    numero: int
    contenido: str
    autor: str
    momento: datetime
    operacion: str
    modelo: str | None = None
    temperatura: float | None = None
    fuentes_rag: list[str] = field(default_factory=list)

    @property
    def momento_legible(self) -> str:
        return self.momento.strftime("%d/%m/%Y %H:%M:%S")

    @property
    def resumen_parametros(self) -> str:
        if not self.modelo:
            return "—"
        temp = f" · temp {self.temperatura}" if self.temperatura is not None else ""
        return f"{self.modelo}{temp}"


@dataclass(frozen=True)
class Comentario:
    autor: str
    rol: str
    texto: str
    momento: datetime
    version_numero: int

    @property
    def momento_legible(self) -> str:
        return self.momento.strftime("%d/%m %H:%M")


@dataclass
class Pieza:
    """Unidad de trabajo: un texto con su historial y sus comentarios."""

    titulo: str
    versiones: list[Version] = field(default_factory=list)
    comentarios: list[Comentario] = field(default_factory=list)
    estado: EstadoPieza = EstadoPieza.BORRADOR

    # -- versiones ----------------------------------------------------------

    @property
    def version_actual(self) -> Version | None:
        return self.versiones[-1] if self.versiones else None

    @property
    def contenido_actual(self) -> str:
        version = self.version_actual
        return version.contenido if version else ""

    def añadir_version(self, contenido: str, autor: str, operacion: str,
                       modelo: str | None = None, temperatura: float | None = None,
                       fuentes_rag: list[str] | None = None) -> Version:
        version = Version(
            numero=len(self.versiones) + 1,
            contenido=contenido,
            autor=autor,
            momento=datetime.now(),
            operacion=operacion,
            modelo=modelo,
            temperatura=temperatura,
            fuentes_rag=fuentes_rag or [],
        )
        self.versiones.append(version)
        return version

    def restaurar(self, numero: int, autor: str) -> Version:
        """Restaura una versión anterior apilando una nueva.

        No se elimina nada: el historial conserva tanto las versiones
        descartadas como el hecho de que hubo una restauración y quién la hizo.
        """
        origen = self.obtener_version(numero)
        return self.añadir_version(
            contenido=origen.contenido,
            autor=autor,
            operacion=f"Restauración de la versión {numero}",
        )

    def obtener_version(self, numero: int) -> Version:
        for version in self.versiones:
            if version.numero == numero:
                return version
        raise KeyError(f"No existe la versión {numero} de «{self.titulo}».")

    # -- comparación --------------------------------------------------------

    def diff(self, desde: int, hasta: int) -> list[tuple[str, str]]:
        """Compara dos versiones palabra a palabra.

        Devuelve una lista de pares (marca, texto) donde la marca es 'igual',
        'añadido' o 'eliminado'. Se compara por palabras y no por líneas porque
        el contenido son párrafos de marketing: un diff por líneas marcaría el
        párrafo entero como cambiado por una coma.
        """
        a = self.obtener_version(desde).contenido.split()
        b = self.obtener_version(hasta).contenido.split()

        matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
        resultado: list[tuple[str, str]] = []

        for etiqueta, i1, i2, j1, j2 in matcher.get_opcodes():
            if etiqueta == "equal":
                resultado.append(("igual", " ".join(a[i1:i2])))
            elif etiqueta == "delete":
                resultado.append(("eliminado", " ".join(a[i1:i2])))
            elif etiqueta == "insert":
                resultado.append(("añadido", " ".join(b[j1:j2])))
            elif etiqueta == "replace":
                resultado.append(("eliminado", " ".join(a[i1:i2])))
                resultado.append(("añadido", " ".join(b[j1:j2])))
        return [(marca, texto) for marca, texto in resultado if texto]

    def estadisticas_diff(self, desde: int, hasta: int) -> dict[str, int]:
        cambios = self.diff(desde, hasta)
        return {
            "añadidas": sum(len(t.split()) for m, t in cambios if m == "añadido"),
            "eliminadas": sum(len(t.split()) for m, t in cambios if m == "eliminado"),
        }

    # -- comentarios y flujo ------------------------------------------------

    def comentar(self, autor: str, rol: str, texto: str) -> Comentario:
        comentario = Comentario(
            autor=autor,
            rol=rol,
            texto=texto,
            momento=datetime.now(),
            version_numero=len(self.versiones),
        )
        self.comentarios.append(comentario)
        return comentario

    def comentarios_de_version(self, numero: int) -> list[Comentario]:
        return [c for c in self.comentarios if c.version_numero == numero]


def crear_pieza_ejemplo() -> Pieza:
    """Pieza precargada para que la demostración arranque con contenido.

    El texto incluye a propósito faltas de ortografía, muletillas de marketing
    prohibidas por la guía de estilo y una cifra sin respaldar, para que las
    cuatro operaciones de edición tengan sobre qué actuar y para que el aviso
    de afirmación no verificable se pueda demostrar.
    """
    pieza = Pieza(titulo="Campaña de verano · Bebidas Aurora")
    pieza.añadir_version(
        contenido=(
            "haber si damos con el mensaje. nuestra nueva bebida es un producto "
            "revolucionario y disruptivo que va a cambiar el mercado por "
            "completo,es una solución 360º para el consumidor moderno. mejora "
            "la hidratación un 40% respecto a la competencia. osea que es "
            "mui superior a todo lo que hay ahora mismo en el lineal."
        ),
        autor="Marc Oliver",
        operacion="Borrador inicial",
    )
    return pieza
