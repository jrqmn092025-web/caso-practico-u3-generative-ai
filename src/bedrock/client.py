"""Wrapper de Amazon Bedrock: construcción de payloads y parseo de respuestas.

Esta es la capa que la memoria denomina *wrapper*. Concentra tres cosas:

1. La construcción de los cuerpos de petición de cada modelo, conforme al
   contrato documentado de Bedrock.
2. La invocación a través de `bedrock-runtime`, sea el cliente real de boto3 o
   el doble de `mock_runtime`.
3. El parseo de las respuestas y la traducción de errores de AWS a errores de
   dominio comprensibles por la interfaz.

Ningún módulo superior construye JSON de Bedrock ni conoce boto3: si mañana
cambiara el contrato de un modelo, el cambio queda contenido aquí.
"""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.bedrock.models import (
    ANTHROPIC_VERSION,
    EMBEDDING_DIMENSIONS,
    IMAGE_DEFAULTS,
    STABLE_DIFFUSION,
    TITAN_EMBEDDINGS,
    ImageStyle,
    InferenceProfile,
)
from src.bedrock.mock_runtime import MockBedrockRuntime, MockValidationError
from src.config import Settings, get_settings


class BedrockError(RuntimeError):
    """Fallo al invocar un modelo, ya sea de validación, permisos o red."""


@dataclass
class InvocationTrace:
    """Registro de una llamada, para trazabilidad y para la interfaz.

    Guardar la petición exacta permite mostrar al evaluador el JSON que se
    habría enviado a AWS, que es la evidencia de que la integración está bien
    planteada aunque no se ejecute contra la nube.
    """

    model_id: str
    request_body: dict[str, Any]
    latency_ms: float
    backend: str
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def request_json(self) -> str:
        return json.dumps(self.request_body, indent=2, ensure_ascii=False)


@dataclass
class TextResult:
    texto: str
    trace: InvocationTrace


@dataclass
class ImageResult:
    png_bytes: bytes
    seed: int
    trace: InvocationTrace


class BedrockClient:
    """Punto único de acceso a los modelos fundacionales."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._runtime = self._build_runtime()

    # -- construcción del transporte ----------------------------------------

    def _build_runtime(self) -> Any:
        """Devuelve el cliente de transporte según el backend configurado.

        Esta función es la **única línea de corte** entre la ejecución simulada
        y la real. Todo lo que hay por encima es idéntico en ambos modos.
        """
        if self.settings.is_mock:
            return MockBedrockRuntime()

        # Camino real: se ejecuta cuando BEDROCK_BACKEND=aws y hay credenciales
        # configuradas (aws configure, variables de entorno o rol de instancia).
        import boto3  # import local: el modo mock no debe exigir credenciales

        if self.settings.aws_profile:
            sesion = boto3.Session(
                profile_name=self.settings.aws_profile,
                region_name=self.settings.aws_region,
            )
        else:
            sesion = boto3.Session(region_name=self.settings.aws_region)
        return sesion.client("bedrock-runtime")

    # -- invocación de bajo nivel -------------------------------------------

    def _invoke(self, model_id: str, body: dict[str, Any]) -> tuple[dict[str, Any], InvocationTrace]:
        payload = json.dumps(body, ensure_ascii=False)
        inicio = time.perf_counter()
        try:
            respuesta = self._runtime.invoke_model(
                modelId=model_id,
                body=payload,
                accept="application/json",
                contentType="application/json",
            )
            crudo = json.loads(respuesta["body"].read())
        except MockValidationError as exc:
            raise BedrockError(
                f"El payload enviado a {model_id} no cumple el contrato del modelo: {exc}"
            ) from exc
        except Exception as exc:  # errores de botocore, red o credenciales
            raise BedrockError(self._traducir_error(model_id, exc)) from exc

        latencia = (time.perf_counter() - inicio) * 1000
        trace = InvocationTrace(
            model_id=model_id,
            request_body=body,
            latency_ms=latencia,
            backend=self.settings.backend,
            usage=crudo.get("usage", {}) if isinstance(crudo, dict) else {},
        )
        return crudo, trace

    @staticmethod
    def _traducir_error(model_id: str, exc: Exception) -> str:
        """Convierte errores de AWS en mensajes accionables.

        Los tres fallos habituales al empezar con Bedrock son: no haber pedido
        acceso al modelo, pedirlo en una región donde no existe, y no tener
        credenciales. Distinguirlos ahorra horas.
        """
        nombre = type(exc).__name__
        texto = str(exc)
        if "AccessDeniedException" in nombre or "AccessDenied" in texto:
            return (
                f"Acceso denegado al modelo {model_id}. Comprueba en la consola de "
                "Bedrock > Model access que el modelo esté habilitado en esta región."
            )
        if "ValidationException" in nombre or "ValidationException" in texto:
            return f"Bedrock rechazó la petición a {model_id}: {texto}"
        if "ResourceNotFound" in nombre or "ResourceNotFound" in texto:
            return (
                f"El modelo {model_id} no existe en la región configurada. "
                "Revisa AWS_REGION."
            )
        if "NoCredentials" in nombre or "credentials" in texto.lower():
            return (
                "No se encontraron credenciales de AWS. Ejecuta `aws configure` o "
                "usa BEDROCK_BACKEND=mock para trabajar sin cuenta."
            )
        if "ThrottlingException" in nombre or "Throttling" in texto:
            return f"Bedrock está limitando la tasa de peticiones a {model_id}. Reintenta en unos segundos."
        return f"Error al invocar {model_id}: {nombre}: {texto}"

    # -- Claude: edición de texto -------------------------------------------

    def invoke_claude(self, *, system_prompt: str, user_content: str,
                      profile: InferenceProfile) -> TextResult:
        """Invoca Claude con la Messages API sobre Bedrock.

        El contenido del usuario ya llega delimitado y saneado por la capa de
        seguridad; aquí solo se ensambla el sobre.
        """
        body: dict[str, Any] = {
            "anthropic_version": ANTHROPIC_VERSION,
            "max_tokens": profile.max_tokens,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": user_content}],
                }
            ],
            "temperature": profile.temperature,
            "top_p": profile.top_p,
        }
        if profile.stop_sequences:
            body["stop_sequences"] = profile.stop_sequences

        crudo, trace = self._invoke(profile.model_id, body)

        bloques = crudo.get("content", [])
        texto = "".join(b.get("text", "") for b in bloques if b.get("type") == "text")
        if not texto:
            raise BedrockError(
                f"{profile.model_id} devolvió una respuesta sin contenido de texto "
                f"(stop_reason={crudo.get('stop_reason')!r})."
            )
        return TextResult(texto=texto.strip(), trace=trace)

    # -- Stable Diffusion: generación de imágenes ---------------------------

    def invoke_stable_diffusion(self, *, prompt: str, style: ImageStyle,
                                seed: int) -> ImageResult:
        """Invoca Stable Diffusion XL con prompt positivo y negativo.

        El prompt negativo se envía como un segundo `text_prompt` con peso
        negativo: es la forma que define el contrato de SDXL en Bedrock, no un
        campo aparte.
        """
        prompt_completo = f"{prompt.strip()}, {style.prompt_suffix}"
        body: dict[str, Any] = {
            "text_prompts": [
                {"text": prompt_completo, "weight": 1.0},
                {"text": style.negative_prompt, "weight": -1.0},
            ],
            "cfg_scale": style.cfg_scale,
            "steps": style.steps,
            "seed": seed,
            "width": IMAGE_DEFAULTS["width"],
            "height": IMAGE_DEFAULTS["height"],
            "samples": IMAGE_DEFAULTS["samples"],
            "style_preset": style.style_preset,
        }

        crudo, trace = self._invoke(STABLE_DIFFUSION, body)

        if crudo.get("result") != "success":
            raise BedrockError(f"Stable Diffusion devolvió result={crudo.get('result')!r}.")
        artefactos = crudo.get("artifacts", [])
        if not artefactos:
            raise BedrockError("Stable Diffusion no devolvió ningún artefacto.")

        artefacto = artefactos[0]
        if artefacto.get("finishReason") == "CONTENT_FILTERED":
            raise BedrockError(
                "El filtro de contenido de Stable Diffusion bloqueó esta generación. "
                "Reformula la descripción."
            )
        return ImageResult(
            png_bytes=base64.b64decode(artefacto["base64"]),
            seed=int(artefacto.get("seed", seed)),
            trace=trace,
        )

    # -- Titan: embeddings para RAG -----------------------------------------

    def invoke_titan_embeddings(self, *, texto: str) -> tuple[list[float], InvocationTrace]:
        body = {
            "inputText": texto,
            "dimensions": EMBEDDING_DIMENSIONS,
            "normalize": True,
        }
        crudo, trace = self._invoke(TITAN_EMBEDDINGS, body)
        vector = crudo.get("embedding")
        if not vector:
            raise BedrockError("Titan no devolvió embedding.")
        return vector, trace
