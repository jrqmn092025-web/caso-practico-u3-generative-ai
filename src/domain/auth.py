"""Roles, permisos y usuarios de demostración.

Alcance declarado
-----------------
Esto es **autorización**, no **autenticación**. El selector de usuario de la
interfaz simula una sesión ya iniciada; no hay contraseñas ni verificación de
identidad, y no debe interpretarse como un control de seguridad real.

En una implantación productiva la autenticación la resolvería un proveedor de
identidad (Amazon Cognito, o el SSO corporativo vía SAML/OIDC), y este módulo
seguiría siendo válido tal cual: recibiría el rol desde el token en lugar de
desde un desplegable. Esa separación entre "quién eres" y "qué puedes hacer" es
la razón de que el módulo esté escrito así.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Permiso(str, Enum):
    """Acciones controlables de la aplicación."""

    GENERAR_IMAGEN = "generar_imagen"
    EDITAR_TEXTO = "editar_texto"
    COMENTAR = "comentar"
    APROBAR = "aprobar"
    RESTAURAR_VERSION = "restaurar_version"
    VER_DIAGNOSTICO = "ver_diagnostico"

    @property
    def descripcion(self) -> str:
        return {
            Permiso.GENERAR_IMAGEN: "Generar imágenes con Stable Diffusion",
            Permiso.EDITAR_TEXTO: "Editar contenido con Claude",
            Permiso.COMENTAR: "Comentar piezas creativas",
            Permiso.APROBAR: "Aprobar o rechazar piezas",
            Permiso.RESTAURAR_VERSION: "Restaurar una versión anterior",
            Permiso.VER_DIAGNOSTICO: "Ver el detalle técnico de las llamadas",
        }[self]


class Rol(str, Enum):
    DISENADOR = "disenador"
    REDACTOR = "redactor"
    APROBADOR = "aprobador"

    @property
    def etiqueta(self) -> str:
        return {
            Rol.DISENADOR: "Diseñador",
            Rol.REDACTOR: "Redactor",
            Rol.APROBADOR: "Aprobador",
        }[self]

    @property
    def descripcion(self) -> str:
        return {
            Rol.DISENADOR: (
                "Genera y selecciona las piezas visuales. No edita el texto de "
                "campaña ni aprueba: su criterio es visual."
            ),
            Rol.REDACTOR: (
                "Trabaja el contenido escrito. No genera imágenes, para que la "
                "dirección visual quede en un solo equipo."
            ),
            Rol.APROBADOR: (
                "Revisa y decide. Puede ver todo y restaurar versiones, pero no "
                "produce contenido: quien aprueba no debe ser quien crea."
            ),
        }[self]


# Matriz de permisos.
#
# El criterio de diseño es la **separación de funciones**: el aprobador no crea
# contenido, y quien crea no se aprueba a sí mismo. Es el mismo principio que
# rige un control de calidad, y evita que la herramienta se convierta en un
# canal de publicación sin revisión.
PERMISOS_POR_ROL: dict[Rol, frozenset[Permiso]] = {
    Rol.DISENADOR: frozenset({
        Permiso.GENERAR_IMAGEN,
        Permiso.COMENTAR,
        Permiso.VER_DIAGNOSTICO,
    }),
    Rol.REDACTOR: frozenset({
        Permiso.EDITAR_TEXTO,
        Permiso.COMENTAR,
        Permiso.VER_DIAGNOSTICO,
    }),
    Rol.APROBADOR: frozenset({
        Permiso.COMENTAR,
        Permiso.APROBAR,
        Permiso.RESTAURAR_VERSION,
        Permiso.VER_DIAGNOSTICO,
    }),
}


@dataclass(frozen=True)
class Usuario:
    id: str
    nombre: str
    rol: Rol

    @property
    def iniciales(self) -> str:
        partes = self.nombre.split()
        return "".join(p[0].upper() for p in partes[:2])

    def puede(self, permiso: Permiso) -> bool:
        return permiso in PERMISOS_POR_ROL[self.rol]


# Plantilla de usuarios para la demostración del flujo colaborativo.
USUARIOS: list[Usuario] = [
    Usuario(id="u1", nombre="Elena Ruiz", rol=Rol.DISENADOR),
    Usuario(id="u2", nombre="Marc Oliver", rol=Rol.REDACTOR),
    Usuario(id="u3", nombre="Nadia Ferrán", rol=Rol.APROBADOR),
    Usuario(id="u4", nombre="Toni Vega", rol=Rol.DISENADOR),
]


def get_usuario(user_id: str) -> Usuario:
    for usuario in USUARIOS:
        if usuario.id == user_id:
            return usuario
    raise KeyError(f"Usuario desconocido: {user_id}")


def usuarios_por_rol(rol: Rol) -> list[Usuario]:
    return [u for u in USUARIOS if u.rol == rol]
