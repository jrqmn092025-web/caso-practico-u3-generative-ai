"""Servicio de generación de imágenes y galería.

Además de invocar Stable Diffusion, este módulo mantiene el catálogo de piezas
generadas con su procedencia completa: prompt, estilo, semilla, modelo y
momento. Guardar la procedencia no es un extra de trazabilidad técnica; es un
requisito que la propia guía de marca impone en su política legal, porque es lo
que permite acreditar cómo se produjo una imagen si alguien lo cuestiona.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime

from src.bedrock.client import BedrockClient, InvocationTrace
from src.bedrock.models import DEFAULT_STYLE, IMAGE_STYLES, ImageStyle
from src.prompts.system_prompts import IMAGE_SAFETY_SUFFIX
from src.security.moderation import moderar_prompt_imagen
from src.services.text_service import ContenidoBloqueado


@dataclass
class ImagenGenerada:
    """Una imagen del catálogo, con su procedencia completa."""

    # Identificador único de esta pieza concreta.
    #
    # Se genera de forma aleatoria y NO se deriva del contenido. Derivarlo del
    # prompt, el estilo o la semilla sería un error: dos generaciones distintas
    # pueden compartir legítimamente semilla y estilo —de hecho es lo habitual,
    # porque la semilla por defecto se mantiene entre generaciones— y acabarían
    # con el mismo identificador. La galería necesita distinguir piezas, no
    # agrupar las que se parecen.
    id: str
    png_bytes: bytes
    prompt_usuario: str
    prompt_enviado: str
    estilo: ImageStyle
    seed: int
    momento: datetime
    autor: str
    trace: InvocationTrace
    avisos_sesgo: list[str] = field(default_factory=list)

    @property
    def momento_legible(self) -> str:
        return self.momento.strftime("%d/%m/%Y %H:%M")

    @property
    def nombre_fichero(self) -> str:
        base = "".join(
            c if c.isalnum() else "_" for c in self.prompt_usuario.lower()[:40]
        ).strip("_")
        return f"{base or 'imagen'}_{self.estilo.clave}_{self.seed}.png"

    @property
    def procedencia(self) -> dict[str, str]:
        """Metadatos que acompañan a la imagen en el catálogo de recursos."""
        return {
            "Generada con IA": "Sí",
            "Modelo": self.trace.model_id,
            "Backend": (
                "Simulado (sin AWS)" if self.trace.backend == "mock"
                else "Amazon Bedrock"
            ),
            "Prompt del usuario": self.prompt_usuario,
            "Estilo": self.estilo.etiqueta,
            "Semilla": str(self.seed),
            "Autor": self.autor,
            "Fecha": self.momento_legible,
        }


class ImageService:
    def __init__(self, client: BedrockClient) -> None:
        self._client = client

    def generar(self, prompt: str, *, estilo_clave: str = DEFAULT_STYLE,
                seed: int | None = None, autor: str = "—") -> ImagenGenerada:
        """Genera una imagen y la devuelve con su procedencia.

        Args:
            seed: semilla concreta, o None para una aleatoria. Fijarla permite
                reproducir exactamente la misma imagen, que es la propiedad que
                convierte la generación en un proceso repetible y auditable.
        """
        if not prompt.strip():
            raise ContenidoBloqueado("Describe la imagen que quieres generar.")

        moderacion = moderar_prompt_imagen(prompt)
        if not moderacion.permitido:
            raise ContenidoBloqueado(moderacion.mensaje)

        estilo = IMAGE_STYLES.get(estilo_clave, IMAGE_STYLES[DEFAULT_STYLE])
        # `secrets` en lugar de `random`: la semilla aleatoria no debe ser
        # predecible entre sesiones, para que dos usuarios que escriban el mismo
        # prompt no obtengan por defecto la misma imagen.
        semilla = seed if seed else secrets.randbelow(4_294_967_295)

        prompt_seguro = f"{prompt.strip()}, {IMAGE_SAFETY_SUFFIX}"
        resultado = self._client.invoke_stable_diffusion(
            prompt=prompt_seguro, style=estilo, seed=semilla
        )

        return ImagenGenerada(
            id=f"img_{secrets.token_hex(6)}",
            png_bytes=resultado.png_bytes,
            prompt_usuario=prompt.strip(),
            prompt_enviado=f"{prompt_seguro}, {estilo.prompt_suffix}",
            estilo=estilo,
            seed=resultado.seed,
            momento=datetime.now(),
            autor=autor,
            trace=resultado.trace,
            avisos_sesgo=moderacion.avisos,
        )
