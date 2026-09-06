"""Doble de pruebas del cliente `bedrock-runtime` de boto3.

Decisión de arquitectura
------------------------
La simulación se aplica en la **frontera de transporte**, no en la lógica de
negocio. `MockBedrockRuntime` expone la misma operación `invoke_model` que el
cliente real de boto3, recibe exactamente el mismo cuerpo JSON que la
aplicación enviaría a AWS y devuelve una respuesta con la misma estructura de
sobre (`{"body": <stream legible>, "contentType": ...}`).

La consecuencia es que todo el código de `src/services/` y `src/bedrock/client.py`
es código de producción: construye payloads reales, los serializa igual y
parsea las respuestas con el mismo camino. Lo único que no ocurre es el viaje
por la red. Cambiar `BEDROCK_BACKEND=mock` por `BEDROCK_BACKEND=aws` no
requiere modificar ninguna otra línea.

Además, este doble **valida** los payloads que recibe contra el contrato
documentado de cada modelo. Si la aplicación construyera una petición mal
formada, el mock falla igual que fallaría AWS, en lugar de devolver una
respuesta plausible y ocultar el error.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import textwrap
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFilter

from src.bedrock.models import (
    CLAUDE_CREATIVE,
    CLAUDE_FAST,
    EMBEDDING_DIMENSIONS,
    STABLE_DIFFUSION,
    TITAN_EMBEDDINGS,
)


class MockValidationError(ValueError):
    """El payload no cumple el contrato documentado del modelo.

    Se distingue de un error genérico para que las pruebas puedan afirmar que
    el mock rechaza peticiones mal formadas.
    """


# ---------------------------------------------------------------------------
# Sobre de respuesta: imita el objeto StreamingBody de botocore
# ---------------------------------------------------------------------------


class _MockStreamingBody:
    """Sustituto de `botocore.response.StreamingBody`.

    boto3 devuelve el cuerpo como un objeto con método `read()` que entrega
    bytes. Replicarlo permite que el código de parseo
    (`json.loads(response["body"].read())`) sea idéntico en ambos backends.
    """

    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)

    def read(self, amt: int | None = None) -> bytes:
        return self._buffer.read() if amt is None else self._buffer.read(amt)

    def close(self) -> None:
        self._buffer.close()


# ---------------------------------------------------------------------------
# Utilidades deterministas
# ---------------------------------------------------------------------------


# Palabras vacías del español y del inglés. Sin este filtro el vector de
# cualquier texto en español queda dominado por preposiciones y artículos.
_STOPWORDS = frozenset("""
a al algo alguna algunas alguno algunos ante antes aqui asi aun aunque cada
como con contra cual cuales cuando de del desde donde dos el ella ellas ellos
en entre era eran eres es esa esas ese eso esos esta estan estas este esto
estos ha hace hacen hacer hasta hay la las le les lo los mas me mi mientras muy
nada ni no nos nuestra nuestro o os otra otras otro otros para pero poco por
porque que quien se ser si sin sobre solo son su sus tambien tan tanto te
tiene tienen todo todos tras un una uno unos ya
a an and are as at be but by for from has have if in is it its of on or that
the their them there these they this to was were what when which who will with
""".split())


def _sin_diacriticos(texto: str) -> str:
    """Elimina tildes y diéresis conservando la eñe como carácter propio."""
    tabla = str.maketrans("áàäâéèëêíìïîóòöôúùüûÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛ",
                          "aaaaeeeeiiiioooouuuuAAAAEEEEIIIIOOOOUUUU")
    return texto.translate(tabla)


# Sufijos flexivos y derivativos del español, ordenados de más largo a más
# corto: el orden importa porque "aciones" debe probarse antes que "es".
_SUFIJOS = (
    "aciones", "amientos", "amiento", "aremos", "eremos", "iremos",
    "ciones", "amente", "abamos", "iamos", "aran", "eran", "iran",
    "ando", "iendo", "aron", "ieron", "amos", "emos", "imos",
    "cion", "sion", "dad", "ista", "ismo", "able", "ible", "oso", "osa",
    "ado", "ada", "ido", "ida", "ar", "er", "ir", "as", "os", "es",
    "an", "en", "ia", "io", "a", "e", "o", "s",
)

# Longitud mínima de la raíz tras truncar. Calibrado empíricamente: con 4, el
# truncador fusionaba "partido" y "partes" en "part", y una consulta sobre
# fútbol recuperaba la sección de paleta cromática. Con 5 se conservan las
# fusiones útiles (colores/color, ahorramos/ahorro, campañas/campaña,
# imágenes/imagen) y desaparece esa colisión. Con 6 se pierden casi todas.
_LONGITUD_MINIMA_RAIZ = 5


def _stem(token: str) -> str:
    """Lematizador por truncamiento de sufijos.

    No es un lematizador lingüístico: es un truncador que reduce las variantes
    flexivas de una misma raíz a una forma común, al estilo de los algoritmos
    de Porter/Snowball. Sin él, el índice trata "color" y "colores" como
    términos sin relación, que fue exactamente el fallo observado al calibrar:
    la consulta "qué colores puedo usar" no recuperaba la sección "Paleta
    cromática".

    Se exige una raíz de al menos cuatro caracteres para no triturar palabras
    cortas ("uso" no debe quedar en "us").
    """
    for sufijo in _SUFIJOS:
        if token.endswith(sufijo) and len(token) - len(sufijo) >= _LONGITUD_MINIMA_RAIZ:
            return token[: -len(sufijo)]
    return token


def _tokenizar(texto: str) -> list[str]:
    """Normaliza, trocea, filtra palabras vacías y reduce a raíces."""
    normalizado = _sin_diacriticos(texto.lower()).replace("ñ", "n")
    return [
        _stem(token)
        for token in re.findall(r"\b[a-z0-9]{3,}\b", normalizado)
        if token not in _STOPWORDS
    ]


def _char_ngrams(token: str, n: int) -> list[str]:
    """N-gramas de caracteres de un token, con marcadores de frontera."""
    if len(token) <= n:
        return [token]
    marcado = f"<{token}>"
    return [marcado[i:i + n] for i in range(len(marcado) - n + 1)]


def _stable_seed(*parts: Any) -> int:
    """Semilla reproducible a partir de cualquier combinación de entradas.

    Se usa un hash criptográfico en lugar de `hash()` porque este último está
    aleatorizado entre procesos en Python y rompería la reproducibilidad entre
    ejecuciones, que es justo la propiedad que queremos demostrar.
    """
    material = "|".join(str(p) for p in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest()[:4], "big")


# ---------------------------------------------------------------------------
# Simulación de Stable Diffusion XL
# ---------------------------------------------------------------------------


class _StableDiffusionSimulator:
    """Genera una imagen determinista a partir del prompt, estilo y semilla.

    No pretende imitar la calidad de Stable Diffusion: pretende demostrar la
    propiedad que el caso práctico pide justificar, es decir, que **la semilla
    controla la reproducibilidad**. Con la misma semilla y el mismo prompt la
    imagen es idéntica; cambiando cualquiera de los dos, cambia.

    La paleta y la geometría derivan del `style_preset`, de modo que los cuatro
    estilos ofrecidos producen resultados visualmente distinguibles.
    """

    PALETTES: dict[str, list[tuple[int, int, int]]] = {
        "photographic": [(38, 45, 58), (92, 108, 122), (168, 176, 178), (214, 206, 190), (240, 236, 228)],
        "anime": [(255, 107, 129), (255, 190, 118), (126, 214, 223), (108, 91, 189), (250, 250, 250)],
        "digital-art": [(94, 46, 30), (168, 96, 40), (206, 158, 78), (72, 88, 66), (232, 214, 178)],
        "line-art": [(23, 42, 58), (58, 110, 165), (240, 84, 79), (247, 201, 72), (245, 245, 240)],
    }

    def render(self, prompt: str, style_preset: str, seed: int,
               width: int, height: int, steps: int, cfg_scale: float) -> Image.Image:
        rnd = _Rng(seed)
        palette = self.PALETTES.get(style_preset, self.PALETTES["photographic"])

        canvas = Image.new("RGB", (width, height), palette[-1])
        draw = ImageDraw.Draw(canvas, "RGBA")

        # El número de formas escala con los pasos de difusión, de modo que el
        # parámetro `steps` tiene un efecto visible, como lo tendría en SDXL.
        shape_count = 12 + int(steps * 0.8)

        for i in range(shape_count):
            color = palette[rnd.randint(0, len(palette) - 1)]
            alpha = 40 + rnd.randint(0, 120)
            cx = rnd.randint(0, width)
            cy = rnd.randint(0, height)
            radius = rnd.randint(width // 20, width // 3)

            if style_preset == "line-art":
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    outline=color + (255,), width=max(2, radius // 24),
                )
            elif style_preset == "anime":
                draw.polygon(
                    self._polygon(cx, cy, radius, 3 + (i % 4), rnd),
                    fill=color + (alpha,),
                )
            elif style_preset == "digital-art":
                # Trazos alargados que evocan pinceladas de impasto.
                draw.ellipse(
                    [cx - radius, cy - radius // 4, cx + radius, cy + radius // 4],
                    fill=color + (alpha,),
                )
            else:
                draw.ellipse(
                    [cx - radius, cy - radius, cx + radius, cy + radius],
                    fill=color + (alpha,),
                )

        # `cfg_scale` alto = mayor adherencia = imagen más nítida.
        blur = max(0.0, (13.0 - cfg_scale) * 0.6)
        if style_preset == "digital-art":
            blur += 1.5  # el óleo difumina los bordes
        if blur > 0:
            canvas = canvas.filter(ImageFilter.GaussianBlur(blur))

        self._stamp(canvas, prompt, style_preset, seed)
        return canvas

    @staticmethod
    def _polygon(cx: int, cy: int, r: int, sides: int, rnd: "_Rng") -> list[tuple[int, int]]:
        rotation = rnd.random() * math.tau
        return [
            (
                int(cx + r * math.cos(rotation + i * math.tau / sides)),
                int(cy + r * math.sin(rotation + i * math.tau / sides)),
            )
            for i in range(sides)
        ]

    @staticmethod
    def _stamp(canvas: Image.Image, prompt: str, style_preset: str, seed: int) -> None:
        """Rotula la imagen como simulada.

        Es una exigencia ética del propio trabajo: una imagen generada por un
        sustituto no debe poder confundirse con una salida real del modelo.
        """
        width, height = canvas.size
        draw = ImageDraw.Draw(canvas, "RGBA")
        band_height = 96
        draw.rectangle([0, height - band_height, width, height], fill=(12, 14, 20, 210))

        resumen = textwrap.shorten(prompt, width=70, placeholder="...")
        lineas = [
            "SALIDA SIMULADA - no procede de Stable Diffusion",
            f"prompt: {resumen}",
            f"style_preset: {style_preset}   |   seed: {seed}",
        ]
        for i, linea in enumerate(lineas):
            draw.text((18, height - band_height + 14 + i * 24), linea, fill=(235, 238, 245, 255))


class _Rng:
    """Generador congruencial lineal, determinista y sin estado global.

    Se evita `random` del sistema para que la reproducibilidad no dependa de la
    semilla global del proceso, que cualquier otra parte del programa podría
    alterar.
    """

    def __init__(self, seed: int) -> None:
        self._state = (seed or 1) % (2**31 - 1)

    def _next(self) -> int:
        self._state = (self._state * 1103515245 + 12345) % (2**31)
        return self._state

    def random(self) -> float:
        return self._next() / (2**31)

    def randint(self, low: int, high: int) -> int:
        if high <= low:
            return low
        return low + self._next() % (high - low + 1)


# ---------------------------------------------------------------------------
# Simulación de Claude
# ---------------------------------------------------------------------------


@dataclass
class _ClaudeSimulator:
    """Aplica transformaciones reales sobre el texto recibido.

    La diferencia con un mock trivial es que la salida **depende del input**:
    el evaluador puede escribir su propio texto y ver que la operación se ha
    aplicado sobre él. Las transformaciones son heurísticas deterministas, no
    inteligencia: eso queda explícito en la respuesta y en la interfaz.
    """

    CORRECCIONES: list[tuple[str, str]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        # Errores frecuentes en castellano; el orden importa (se aplican en cadena).
        self.CORRECCIONES = [
            (r"\bhaber si\b", "a ver si"),
            (r"\bosea\b", "o sea"),
            (r"\bde que\b", "de que"),
            (r"\bsolo\b", "solo"),
            (r"\bhechar\b", "echar"),
            (r"\bhay que ver\b", "hay que ver"),
            (r"\s+([,.;:!?])", r"\1"),          # espacio antes de puntuación
            (r"([,.;:])(?=[^\s\d])", r"\1 "),   # falta de espacio tras puntuación
            (r"\s{2,}", " "),                    # espacios múltiples
            (r"\bmui\b", "muy"),
            (r"\bpor que\b(?=\s+[a-záéíóúñ])", "porque"),
        ]

    # -- despacho -----------------------------------------------------------

    def responder(self, system: str, user_text: str, temperature: float,
                  model_id: str, seed: int) -> str:
        tarea = self._detectar_tarea(system, user_text)
        cuerpo = self._extraer_contenido(user_text)

        if not cuerpo.strip():
            return "No se ha recibido texto sobre el que trabajar."

        if tarea == "resumir":
            return self._resumir(cuerpo)
        if tarea == "expandir":
            return self._expandir(cuerpo, seed)
        if tarea == "corregir":
            return self._corregir(cuerpo)
        if tarea == "variar":
            return self._variar(cuerpo, temperature, seed)
        return self._corregir(cuerpo)

    @staticmethod
    def _detectar_tarea(system: str, user_text: str) -> str:
        combinado = f"{system}\n{user_text}".lower()
        for clave in ("resumir", "expandir", "corregir", "variar"):
            if f"tarea: {clave}" in combinado:
                return clave
        return "corregir"

    @staticmethod
    def _extraer_contenido(user_text: str) -> str:
        """Recupera el texto delimitado por las etiquetas de la aplicación.

        El wrapper encierra el contenido del usuario entre `<contenido>` y
        `</contenido>` como defensa frente a inyección de prompt. El simulador
        respeta ese contrato: solo trabaja sobre lo que hay dentro.
        """
        match = re.search(r"<contenido>(.*?)</contenido>", user_text, re.DOTALL)
        return match.group(1).strip() if match else user_text.strip()

    # -- operaciones --------------------------------------------------------

    @staticmethod
    def _frases(texto: str) -> list[str]:
        partes = re.split(r"(?<=[.!?])\s+", texto.strip())
        return [p.strip() for p in partes if p.strip()]

    def _resumir(self, texto: str) -> str:
        frases = self._frases(texto)
        if len(frases) <= 2:
            return texto.strip()

        # Puntuación por posición (la primera y la última pesan) y por densidad
        # de términos frecuentes: una aproximación extractiva clásica.
        palabras = re.findall(r"\b\w{5,}\b", texto.lower())
        frecuencias: dict[str, int] = {}
        for palabra in palabras:
            frecuencias[palabra] = frecuencias.get(palabra, 0) + 1

        puntuadas = []
        for i, frase in enumerate(frases):
            score = sum(frecuencias.get(w, 0) for w in re.findall(r"\b\w{5,}\b", frase.lower()))
            if i == 0:
                score *= 1.6
            elif i == len(frases) - 1:
                score *= 1.2
            puntuadas.append((score / max(len(frase.split()), 1), i, frase))

        objetivo = max(1, round(len(frases) * 0.4))
        elegidas = sorted(sorted(puntuadas, reverse=True)[:objetivo], key=lambda t: t[1])
        return " ".join(frase for _, _, frase in elegidas)

    def _expandir(self, texto: str, seed: int) -> str:
        frases = self._frases(texto)
        rnd = _Rng(seed)
        desarrollos = [
            "Conviene detallar este punto con un ejemplo concreto que el lector pueda reconocer.",
            "El beneficio para el destinatario final merece explicitarse en lugar de darse por supuesto.",
            "Este argumento gana fuerza si se acompaña de una cifra o una referencia verificable.",
            "Aquí encaja una objeción previsible del lector y su respuesta.",
            "Merece la pena conectar esta idea con la propuesta de valor de la marca.",
        ]
        salida = []
        for i, frase in enumerate(frases):
            salida.append(frase)
            if i % 2 == 0:
                salida.append(desarrollos[rnd.randint(0, len(desarrollos) - 1)])
        cierre = (
            "\n\nEn conjunto, el texto sostiene una tesis clara; el desarrollo anterior "
            "la apuntala sin desviarse del mensaje original."
        )
        return " ".join(salida) + cierre

    def _corregir(self, texto: str) -> str:
        corregido = texto
        for patron, reemplazo in self.CORRECCIONES:
            corregido = re.sub(patron, reemplazo, corregido, flags=re.IGNORECASE)

        # Mayúscula inicial de cada oración.
        def _capitalizar(match: re.Match[str]) -> str:
            return match.group(1) + match.group(2).upper()

        corregido = re.sub(r"(^|[.!?]\s+)([a-záéíóúñ])", _capitalizar, corregido)
        if corregido and not corregido.rstrip().endswith((".", "!", "?", ":")):
            corregido = corregido.rstrip() + "."
        return corregido.strip()

    def _variar(self, texto: str, temperature: float, seed: int) -> str:
        aperturas = [
            ("Versión directa", "Al grano: "),
            ("Versión narrativa", "Imagina la escena. "),
            ("Versión orientada a beneficio", "Lo que esto significa para ti: "),
        ]
        # La temperatura controla cuántas variaciones se ofrecen: es la forma
        # visible de que el parámetro tiene consecuencias en la aplicación.
        cantidad = 3 if temperature >= 0.7 else 2
        base = self._frases(texto)
        rnd = _Rng(seed)

        bloques = []
        for i in range(cantidad):
            etiqueta, apertura = aperturas[i % len(aperturas)]
            reordenadas = base[:]
            if len(reordenadas) > 2 and i > 0:
                pivote = rnd.randint(1, len(reordenadas) - 1)
                reordenadas = reordenadas[pivote:] + reordenadas[:pivote]
            bloques.append(f"**{etiqueta}**\n{apertura}{' '.join(reordenadas)}")
        return "\n\n".join(bloques)


# ---------------------------------------------------------------------------
# Cliente simulado
# ---------------------------------------------------------------------------


class MockBedrockRuntime:
    """Sustituto de `boto3.client("bedrock-runtime")`.

    Solo implementa `invoke_model`, que es la única operación que la aplicación
    utiliza. Cualquier otra llamada falla de forma explícita en lugar de
    devolver silencio, para que una divergencia entre backends se detecte.
    """

    def __init__(self) -> None:
        self._sd = _StableDiffusionSimulator()
        self._claude = _ClaudeSimulator()
        self.llamadas: list[dict[str, Any]] = []

    # -- API pública (contrato de boto3) ------------------------------------

    def invoke_model(self, *, modelId: str, body: str | bytes,
                     accept: str = "application/json",
                     contentType: str = "application/json") -> dict[str, Any]:
        payload = json.loads(body)
        self.llamadas.append({"modelId": modelId, "body": payload})

        if modelId in (CLAUDE_FAST, CLAUDE_CREATIVE):
            respuesta = self._invoke_claude(modelId, payload)
        elif modelId == STABLE_DIFFUSION:
            respuesta = self._invoke_stable_diffusion(payload)
        elif modelId == TITAN_EMBEDDINGS:
            respuesta = self._invoke_titan(payload)
        else:
            raise MockValidationError(
                f"modelId no reconocido por el simulador: {modelId!r}. "
                "Añádelo al catálogo de src/bedrock/models.py."
            )

        return {
            "body": _MockStreamingBody(json.dumps(respuesta).encode("utf-8")),
            "contentType": "application/json",
            "ResponseMetadata": {"HTTPStatusCode": 200, "RetryAttempts": 0},
        }

    # -- validación + simulación por modelo ---------------------------------

    def _invoke_claude(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._exigir(payload, "anthropic_version", str)
        self._exigir(payload, "max_tokens", int)
        self._exigir(payload, "messages", list)

        if payload["anthropic_version"] != "bedrock-2023-05-31":
            raise MockValidationError(
                "anthropic_version debe ser 'bedrock-2023-05-31' en Bedrock."
            )
        if not payload["messages"]:
            raise MockValidationError("El array 'messages' no puede estar vacío.")

        temperatura = payload.get("temperature", 1.0)
        if not 0.0 <= temperatura <= 1.0:
            raise MockValidationError(
                f"temperature fuera de rango [0.0, 1.0]: {temperatura}"
            )

        primer_mensaje = payload["messages"][0]
        if primer_mensaje.get("role") != "user":
            raise MockValidationError("El primer mensaje debe tener role='user'.")

        contenido = primer_mensaje["content"]
        if isinstance(contenido, list):
            texto_usuario = "\n".join(
                bloque.get("text", "") for bloque in contenido
                if bloque.get("type") == "text"
            )
        else:
            texto_usuario = str(contenido)

        system = payload.get("system", "")
        seed = _stable_seed(system, texto_usuario, temperatura, model_id)
        texto = self._claude.responder(system, texto_usuario, temperatura, model_id, seed)

        # Sobre de respuesta de la Messages API en Bedrock.
        return {
            "id": f"msg_mock_{seed:08x}",
            "type": "message",
            "role": "assistant",
            "model": model_id,
            "content": [{"type": "text", "text": texto}],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": max(1, len(texto_usuario) // 4),
                "output_tokens": max(1, len(texto) // 4),
            },
        }

    def _invoke_stable_diffusion(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._exigir(payload, "text_prompts", list)
        if not payload["text_prompts"]:
            raise MockValidationError("text_prompts no puede estar vacío.")

        positivos = [p for p in payload["text_prompts"] if p.get("weight", 1) > 0]
        if not positivos:
            raise MockValidationError(
                "Se requiere al menos un prompt con weight positivo."
            )

        cfg = float(payload.get("cfg_scale", 7))
        if not 0 < cfg <= 35:
            raise MockValidationError(f"cfg_scale fuera de rango (0, 35]: {cfg}")

        steps = int(payload.get("steps", 30))
        if not 10 <= steps <= 150:
            raise MockValidationError(f"steps fuera de rango [10, 150]: {steps}")

        width = int(payload.get("width", 1024))
        height = int(payload.get("height", 1024))
        seed = int(payload.get("seed", 0)) or _stable_seed(positivos[0]["text"])
        preset = payload.get("style_preset", "photographic")

        imagen = self._sd.render(
            prompt=positivos[0]["text"],
            style_preset=preset,
            seed=seed,
            width=width,
            height=height,
            steps=steps,
            cfg_scale=cfg,
        )
        buffer = io.BytesIO()
        imagen.save(buffer, format="PNG", optimize=True)
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        # Sobre de respuesta de SDXL en Bedrock.
        return {
            "result": "success",
            "artifacts": [
                {"seed": seed, "base64": b64, "finishReason": "SUCCESS"}
            ],
        }

    def _invoke_titan(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._exigir(payload, "inputText", str)
        texto = payload["inputText"]
        if not texto.strip():
            raise MockValidationError("inputText no puede estar vacío.")

        dimensiones = int(payload.get("dimensions", EMBEDDING_DIMENSIONS))
        vector = self._embedding_deterministico(texto, dimensiones)
        if payload.get("normalize", True):
            norma = math.sqrt(sum(v * v for v in vector)) or 1.0
            vector = [v / norma for v in vector]

        return {
            "embedding": vector,
            "inputTextTokenCount": max(1, len(texto) // 4),
        }

    @staticmethod
    def _embedding_deterministico(texto: str, dimensiones: int) -> list[float]:
        """Embedding léxico con proyección por hash (*hashing trick*).

        Limitación declarada
        --------------------
        Esto **no** captura semántica: no sabe que "cromática" y "color" están
        relacionadas salvo por coincidencia de caracteres. Titan sí lo haría.
        Lo que este sustituto garantiza es la propiedad que el RAG necesita para
        ser demostrable de extremo a extremo: textos con vocabulario común
        quedan próximos, textos ajenos al corpus quedan lejos, y la similitud
        coseno los ordena de forma estable.

        Tres decisiones lo hacen funcionar como recuperador léxico decente:

        1. **Palabras vacías fuera.** Sin este filtro, "de", "la" y "que"
           dominan el vector y cualquier texto en español se parece a cualquier
           otro. Fue el fallo observado en la primera versión: una consulta sin
           relación con el corpus obtenía la similitud más alta por acumulación
           de preposiciones.
        2. **Diacríticos normalizados.** "campaña" y "campana", "gráfica" y
           "grafica" deben colisionar: en una herramienta interna la gente
           escribe sin tildes.
        3. **N-gramas de caracteres además de palabras.** Aproximan la
           morfología del español (color/colores/coloración) sin necesidad de
           un lematizador, con peso menor que el token completo.
        """
        vector = [0.0] * dimensiones
        tokens = _tokenizar(texto)
        if not tokens:
            return vector

        # Frecuencia sublineal: la décima aparición de un término aporta mucho
        # menos que la segunda.
        frecuencias: dict[str, int] = {}
        for token in tokens:
            frecuencias[token] = frecuencias.get(token, 0) + 1

        def _proyectar(rasgo: str, peso: float) -> None:
            digest = hashlib.sha256(rasgo.encode("utf-8")).digest()
            for repeticion in range(3):  # tres proyecciones reducen colisiones
                offset = repeticion * 8
                indice = int.from_bytes(digest[offset:offset + 4], "big") % dimensiones
                signo = 1.0 if digest[offset + 4] % 2 == 0 else -1.0
                vector[indice] += signo * peso

        for token, frecuencia in frecuencias.items():
            peso = 1.0 + math.log(frecuencia)
            _proyectar(f"w:{token}", peso)
            for ngrama in _char_ngrams(token, 4):
                _proyectar(f"n:{ngrama}", peso * 0.35)

        return vector

    @staticmethod
    def _exigir(payload: dict[str, Any], clave: str, tipo: type) -> None:
        if clave not in payload:
            raise MockValidationError(f"Falta el campo obligatorio '{clave}'.")
        if not isinstance(payload[clave], tipo):
            raise MockValidationError(
                f"El campo '{clave}' debe ser {tipo.__name__}, "
                f"se recibió {type(payload[clave]).__name__}."
            )
