"""Configuración central de la aplicación.

Toda la parametrización que cambia entre entornos (backend de Bedrock, región,
semilla, RAG) se resuelve aquí y en un único punto, para que ningún módulo de
negocio tenga que leer variables de entorno por su cuenta.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BRAND_GUIDE_DIR = DATA_DIR / "brand_guide"
GENERATED_DIR = DATA_DIR / "generated"
ASSETS_DIR = BASE_DIR / "assets"
PDFS_DIR = BASE_DIR / "pdfs"   # Documentos entregables, en PDF


def _load_dotenv() -> None:
    """Carga un `.env` si existe, sin dependencias externas.

    Se mantiene deliberadamente simple: el proyecto no necesita `python-dotenv`
    para leer cinco claves.
    """
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def _as_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


@dataclass(frozen=True)
class Settings:
    """Instantánea inmutable de la configuración efectiva."""

    backend: str
    aws_region: str
    aws_profile: str | None
    default_seed: int
    rag_enabled: bool

    @property
    def is_mock(self) -> bool:
        return self.backend == "mock"

    @property
    def backend_label(self) -> str:
        return "Simulado (mock)" if self.is_mock else f"AWS Bedrock · {self.aws_region}"


def get_settings() -> Settings:
    backend = os.environ.get("BEDROCK_BACKEND", "mock").strip().lower()
    if backend not in {"mock", "aws"}:
        raise ValueError(
            f"BEDROCK_BACKEND debe ser 'mock' o 'aws', se recibió {backend!r}."
        )
    return Settings(
        backend=backend,
        aws_region=os.environ.get("AWS_REGION", "us-east-1").strip(),
        aws_profile=os.environ.get("AWS_PROFILE") or None,
        default_seed=int(os.environ.get("DEFAULT_SEED", "0") or 0),
        rag_enabled=_as_bool(os.environ.get("RAG_ENABLED", "true"), True),
    )


def ensure_runtime_dirs() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
