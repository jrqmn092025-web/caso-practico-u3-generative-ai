"""Aplica cambios sobre docs/Nucleo_Aurora_Studio.docx conservando lo ya escrito.

    python scripts/actualizar_nucleo.py

Por qué este script y no una regeneración
------------------------------------------
`generar_memoria.py` construye el documento desde cero. Tras su primera
generación, el documento fue revisado y ampliado a mano: se reformuló la
portada, se numeraron los epígrafes de segundo nivel, se sustituyeron las rayas
por paréntesis explicativos y se incorporaron aclaraciones dirigidas a un lector
sin formación técnica. Regenerar descartaría todo ese trabajo.

Este script opera en el sentido contrario: abre el documento existente y
modifica únicamente lo necesario, dejando intacto el resto. Es idempotente —
puede ejecutarse varias veces sin duplicar contenido— porque comprueba la
presencia de cada bloque antes de insertarlo.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402
from docx.shared import Cm, Pt  # noqa: E402

from src.config import DOCS_DIR  # noqa: E402

# Se reutilizan los ayudantes de formato del generador original para que los
# bloques nuevos sean tipográficamente indistinguibles de los existentes.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_memoria import (  # noqa: E402
    GRIS,
    bloque_codigo,
    caja_destacada,
    parrafo,
    parrafo_rico,
    tabla,
    vineta,
    vineta_rica,
)

DOCUMENTO = DOCS_DIR / "Nucleo_Aurora_Studio.docx"


# ---------------------------------------------------------------------------
# Utilidades de edición en el sitio
# ---------------------------------------------------------------------------


def reemplazar(parrafo_o_celda, viejo: str, nuevo: str) -> bool:
    """Sustituye texto conservando el formato de los tramos.

    Actúa primero a nivel de tramo (`run`), que es donde vive el formato. Solo
    si el término aparece partido entre varios tramos recurre a reescribir el
    párrafo completo, lo que implica perder las negritas internas; por eso se
    informa de ello al ejecutar.
    """
    parrafos = (
        parrafo_o_celda.paragraphs
        if hasattr(parrafo_o_celda, "paragraphs")
        else [parrafo_o_celda]
    )
    cambiado = False
    for p in parrafos:
        if viejo not in p.text:
            continue
        for run in p.runs:
            if viejo in run.text:
                run.text = run.text.replace(viejo, nuevo)
                cambiado = True
                break
        else:
            # El término cruza la frontera entre tramos: se reconstruye.
            texto = p.text.replace(viejo, nuevo)
            for run in list(p.runs)[1:]:
                run._element.getparent().remove(run._element)
            if p.runs:
                p.runs[0].text = texto
            cambiado = True
            print(f"      (aviso: '{viejo[:30]}' cruzaba tramos; formato interno perdido)")
    return cambiado


def reemplazar_en_documento(doc, viejo: str, nuevo: str) -> int:
    n = 0
    for p in doc.paragraphs:
        if reemplazar(p, viejo, nuevo):
            n += 1
    for t in doc.tables:
        for fila in t.rows:
            vistas = set()
            for celda in fila.cells:
                if id(celda._tc) in vistas:
                    continue
                vistas.add(id(celda._tc))
                if reemplazar(celda, viejo, nuevo):
                    n += 1
    return n


def buscar_parrafo(doc, fragmento: str, estilo: str | None = None):
    for p in doc.paragraphs:
        if fragmento in p.text and (estilo is None or (p.style and p.style.name == estilo)):
            return p
    return None


def recolectar(doc, constructor) -> list:
    """Ejecuta `constructor`, que añade bloques al final, y los devuelve."""
    antes = list(doc.element.body.iterchildren())
    constructor()
    despues = list(doc.element.body.iterchildren())
    return [el for el in despues if el not in antes]


def mover_antes(referencia, elementos) -> None:
    for el in elementos:
        referencia._p.addprevious(el)


def mover_despues(referencia, elementos) -> None:
    ancla = referencia._p
    for el in elementos:
        ancla.addnext(el)
        ancla = el


# ---------------------------------------------------------------------------
# 1 · Precisión terminológica
# ---------------------------------------------------------------------------


def corregir_terminologia(doc) -> None:
    print("1. Precisión terminológica")

    # 'proveedor' designaba dos referentes distintos en la misma sección: los
    # proveedores de modelos (Anthropic, Stability AI, Amazon) y el servicio que
    # los expone (AWS). Se reserva el término para los primeros.
    sustituciones = [
        ("del mismo modo que lo haría el proveedor",
         "del mismo modo que lo haría Amazon Bedrock"),
        ("aplicando los mismos criterios que el proveedor",
         "aplicando los mismos criterios que Amazon Bedrock"),
        ("Traducción de los errores del proveedor a mensajes accionables",
         "Traducción de los errores del servicio a mensajes accionables"),
        ("formatos de petición y respuesta por proveedor",
         "formatos de petición y respuesta por proveedor de modelos"),
        ("dependencia de un proveedor único",
         "dependencia de un único proveedor de servicios en la nube"),
        # 'el sustituto' aparecía sin antecedente en un recuadro que se lee de
        # forma aislada.
        ("El sustituto valida cada petición recibida",
         "El doble de transporte (la clase MockBedrockRuntime) valida cada "
         "petición recibida"),
    ]
    for viejo, nuevo in sustituciones:
        n = reemplazar_en_documento(doc, viejo, nuevo)
        estado = f"{n} sustitución(es)" if n else "no encontrado (¿ya aplicado?)"
        print(f"   · {viejo[:52]:<54} {estado}")


# ---------------------------------------------------------------------------
# 2 · Desarrollo del pasaje sobre razonamiento adaptativo
# ---------------------------------------------------------------------------


def desarrollar_razonamiento_adaptativo(doc) -> None:
    print("2. Desarrollo del pasaje sobre razonamiento adaptativo")

    ancla = buscar_parrafo(doc, "Su adopción habría impedido demostrar el control")
    if ancla is None:
        print("   · párrafo ancla no encontrado; se omite")
        return
    if buscar_parrafo(doc, "distribución de probabilidad sobre el siguiente"):
        print("   · ya desarrollado; se omite")
        return

    def constructor():
        parrafo(doc,
                "Conviene explicitar en qué consiste esa diferencia, dado que "
                "constituye el fundamento de la elección. En el enfoque clásico, el "
                "modelo calcula en cada paso una distribución de probabilidad sobre "
                "el siguiente fragmento de texto que va a escribir. La temperatura "
                "reescala esa distribución: un valor bajo la vuelve puntiaguda, de "
                "modo que resulta elegido casi siempre el fragmento más probable y "
                "la salida es prácticamente determinista; un valor alto la aplana y "
                "permite la entrada de alternativas menos probables, que es lo que "
                "produce diversidad. Top-P actúa por truncamiento, descartando la "
                "cola de opciones improbables. Lo que se controla, en definitiva, es "
                "el modo en que se elige cada fragmento.")
        parrafo(doc,
                "El enfoque adoptado por los modelos más recientes desplaza ese "
                "control a otro plano. El razonamiento adaptativo consiste en que el "
                "modelo delibera internamente antes de responder y decide por sí "
                "mismo cuánto conviene deliberar según la dificultad de la petición, "
                "sin cuota previa fijada por el programador. El parámetro de esfuerzo "
                "es la palanca que gobierna esa deliberación: admite niveles de "
                "menor a mayor intensidad y regula tanto la profundidad del "
                "razonamiento como el consumo total de recursos. El control pasa así "
                "de la selección de cada fragmento al proceso de deliberación previo "
                "a la respuesta.")
        caja_destacada(
            doc,
            "Consecuencia sobre la elección de modelo",
            "Ambos enfoques son mutuamente excluyentes por diseño: los modelos que "
            "incorporan razonamiento adaptativo no ignoran el parámetro de "
            "temperatura, sino que lo rechazan devolviendo un error. Su adopción "
            "habría dejado el trabajo sin el objeto de estudio de la unidad, dado "
            "que no existiría temperatura alguna que justificar. La elección de "
            "Claude Haiku 4.5 y Claude Sonnet 4.6 no responde, por tanto, a un "
            "criterio conservador, sino a la alineación con aquello que la unidad "
            "evalúa.",
            "E8F0F8",
        )

    mover_despues(ancla, recolectar(doc, constructor))
    print("   · añadidos dos párrafos explicativos y un recuadro")


# ---------------------------------------------------------------------------
# 3 · Aclaración del término «canónico»
# ---------------------------------------------------------------------------


def aclarar_canonico(doc) -> None:
    print("3. Aclaración del término «canónico»")
    n = reemplazar_en_documento(
        doc,
        "Se trata, por tanto, del caso de uso canónico de la generación aumentada "
        "por recuperación:",
        "Se trata, por tanto, del caso para el que la generación aumentada por "
        "recuperación fue concebida, es decir, de su caso de uso canónico:",
    )
    print(f"   · {'reformulado' if n else 'no encontrado (¿ya aplicado?)'}")


# ---------------------------------------------------------------------------
# 4 · Párrafo sobre las aportaciones adicionales
# ---------------------------------------------------------------------------


def añadir_aportaciones(doc) -> None:
    print("4. Aportaciones adicionales respecto a lo exigido en la guía")

    if buscar_parrafo(doc, "asistente especializado durante el desarrollo"):
        print("   · ya presente; se omite")
        return

    ancla = buscar_parrafo(doc, "La estructura del documento responde al orden")
    if ancla is None:
        print("   · párrafo ancla no encontrado; se omite")
        return

    def constructor():
        parrafo(doc,
                "La solución entregada excede en varios aspectos lo estrictamente "
                "exigido por la guía. Dichas ampliaciones no obedecen a un afán de "
                "extensión, sino que surgieron del propio proceso de diseño al "
                "emplear un asistente especializado durante el desarrollo, en el "
                "papel de consultor técnico: cada decisión relevante fue sometida a "
                "discusión, lo que hizo aflorar riesgos y alternativas que el "
                "enunciado no plantea de forma explícita. Se relacionan a "
                "continuación, con indicación del apartado donde se desarrollan.")

        tabla(doc,
              ["Aportación adicional", "Motivo", "Apartado"],
              [
                  ["Cuarta figura de usuario: el responsable legal",
                   "Los requisitos de trazabilidad y derechos de autor carecían de "
                   "un actor que los demandara.", "3.1.2"],
                  ["Sustitución en la frontera de transporte con validación de "
                   "contratos",
                   "Permite acreditar la corrección de la integración sin ejecutar "
                   "contra la nube, en lugar de limitarse a afirmarla.", "3.2"],
                  ["Cuarto estilo de imagen: ilustración editorial",
                   "El enunciado solicita tres estilos; se añade el registro más "
                   "frecuente en campañas digitales.", "3.3"],
                  ["Calibración empírica del umbral de recuperación",
                   "Evita fijar un valor arbitrario: se mide sobre consultas "
                   "legítimas y de ruido, y el procedimiento es reproducible.",
                   "3.5"],
                  ["Moderación también sobre la respuesta generada",
                   "Una petición inocua puede producir una salida inadecuada; "
                   "filtrar solo la entrada resulta insuficiente.", "3.6"],
                  ["Conjunto de veinte pruebas automatizadas",
                   "Verifican la forma de las peticiones a los tres modelos y el "
                   "comportamiento de los controles de seguridad.", "4"],
                  ["Generación del diagrama y de esta memoria desde el código",
                   "La tabla de parámetros se lee de los módulos, lo que impide "
                   "que documento e implementación diverjan.", "4"],
                  ["Requisitos para el paso a producción y glosario",
                   "Facilitan la lectura del documento por perfiles no técnicos y "
                   "sitúan el trabajo ante un despliegue real.", "7 y 9"],
              ],
              anchos=[6.4, 8.0, 1.6])

        parrafo(doc,
                "Se hace constar el uso de dicho asistente por transparencia "
                "metodológica. Las decisiones de diseño, su justificación y la "
                "redacción final son responsabilidad del autor; la herramienta operó "
                "como interlocutor técnico, no como sustituto del criterio.",
                tamano=10, color=GRIS)

    mover_despues(ancla, recolectar(doc, constructor))
    print("   · añadidos párrafo introductorio, tabla de ocho aportaciones y nota")


# ---------------------------------------------------------------------------
# 5 · Los cuatro pilares aplicados a la generación de imágenes
# ---------------------------------------------------------------------------


def añadir_pilares_imagen(doc) -> None:
    print("5. Aplicabilidad de los cuatro pilares a la generación de imágenes")

    if buscar_parrafo(doc, "Stable Diffusion no admite instrucciones de sistema"):
        print("   · ya presente; se omite")
        return

    ancla = buscar_parrafo(doc, "Instrucciones completas", estilo="Heading 2")
    if ancla is None:
        print("   · encabezado ancla no encontrado; se omite")
        return

    def constructor():
        doc.add_heading("Aplicabilidad de los cuatro pilares a la generación de "
                        "imágenes", level=2)

        parrafo(doc,
                "La tabla anterior se refiere exclusivamente a las operaciones de "
                "texto. La omisión de la generación de imágenes es deliberada y "
                "requiere justificación, por cuanto podría interpretarse como una "
                "laguna del diseño.")

        parrafo(doc,
                "El marco de los cuatro pilares describe la construcción de unas "
                "instrucciones de sistema, y estas constituyen un mecanismo propio "
                "de los modelos de lenguaje conversacionales: un texto persistente "
                "que fija el comportamiento del asistente a lo largo de la "
                "interacción. Stable Diffusion no admite instrucciones de sistema. "
                "No se le instruye, sino que se le condiciona: recibe una "
                "descripción, un conjunto de parámetros numéricos y una semilla, y "
                "devuelve una imagen. No existe en él un canal separado que permita "
                "distinguir entre lo que el sistema ordena y lo que el usuario pide.")

        parrafo(doc,
                "Aplicar el marco de forma literal habría supuesto, por tanto, "
                "atribuir al modelo de difusión una capacidad que no posee. Ahora "
                "bien, las cuatro funciones que los pilares cumplen sí tienen "
                "equivalente en la generación de imágenes, aunque se materialicen "
                "por otros medios. La correspondencia es la siguiente.")

        tabla(doc,
              ["Pilar", "Equivalente en la generación de imágenes", "Dónde se implementa"],
              [
                  ["Rol / persona",
                   "El preajuste de estilo (style_preset) y el sufijo de prompt "
                   "asociado, que fijan el registro visual de la pieza del mismo "
                   "modo que la persona fija el registro del texto.",
                   "IMAGE_STYLES en src/bedrock/models.py"],
                  ["Objetivo",
                   "La descripción aportada por el usuario, saneada y ampliada con "
                   "el sufijo del estilo seleccionado.",
                   "ImageService.generar()"],
                  ["Restricciones",
                   "El prompt negativo, transmitido como un segundo elemento de "
                   "text_prompts con peso −1.0, junto al sufijo de seguridad que "
                   "excluye logotipos, marcas de agua y personas reconocibles. Los "
                   "controles sobre marcas registradas y estilos de autor operan "
                   "antes de la invocación.",
                   "IMAGE_SAFETY_SUFFIX y moderar_prompt_imagen()"],
                  ["Formato de salida",
                   "No es negociable mediante instrucciones: lo determina el "
                   "contrato del modelo, que devuelve una imagen codificada en "
                   "base64 dentro del campo artifacts. Lo que sí se controla son "
                   "sus propiedades: resolución, número de muestras, escala de guía "
                   "y pasos de difusión.",
                   "IMAGE_DEFAULTS y el perfil de cada estilo"],
              ],
              anchos=[2.8, 8.6, 4.6])

        caja_destacada(
            doc,
            "Consecuencia sobre la arquitectura",
            "La diferencia tiene un efecto directo en la defensa frente a la "
            "inyección de instrucciones. En las operaciones de texto, dicha defensa "
            "se apoya en un canal de sistema separado del contenido del usuario. En "
            "la generación de imágenes ese canal no existe, de modo que la "
            "protección debe aplicarse íntegramente antes de invocar al modelo, "
            "mediante la moderación de la descripción y la incorporación forzosa del "
            "prompt negativo. Es la razón por la que los controles de marcas "
            "registradas y estilos de autor bloquean la petición en lugar de "
            "limitarse a advertir.",
            "FFF4E5",
        )

    mover_antes(ancla, recolectar(doc, constructor))
    print("   · añadido epígrafe con justificación, tabla de equivalencias y recuadro")


# ---------------------------------------------------------------------------
# 6 · Requisitos para el paso a producción
# ---------------------------------------------------------------------------


def añadir_produccion(doc) -> None:
    print("6. Requisitos para el paso a producción")

    if buscar_parrafo(doc, "Requisitos para el paso a producción", estilo="Heading 1"):
        print("   · ya presente; se omite")
        return

    ancla = buscar_parrafo(doc, "Fuentes y herramientas", estilo="Heading 1")
    if ancla is None:
        print("   · encabezado de fuentes no encontrado; se omite")
        return

    def constructor():
        doc.add_heading("7. Requisitos para el paso a producción", level=1)

        parrafo(doc,
                "La aplicación entregada se ejecuta en modo simulado sobre un único "
                "equipo. Su puesta en servicio real exigiría cubrir los requisitos "
                "que se relacionan a continuación, agrupados por naturaleza y "
                "ordenados según su carácter bloqueante. Los tres primeros bloques "
                "son condición necesaria para que la aplicación funcione; los "
                "restantes lo son para que funcione de manera responsable.")

        doc.add_heading("Acceso a los modelos", level=2)
        tabla(doc,
              ["Requisito", "Detalle", "Carácter"],
              [
                  ["Cuenta de Amazon Web Services",
                   "Con método de pago asociado. Amazon Bedrock no se incluye en el "
                   "nivel gratuito: la facturación se produce desde la primera "
                   "invocación.", "Bloqueante"],
                  ["Concesión de acceso a los modelos",
                   "Solicitud expresa en la consola de Bedrock para Anthropic "
                   "Claude, Stability AI Stable Diffusion y Amazon Titan "
                   "Embeddings. La concesión es independiente por cada región.",
                   "Bloqueante"],
                  ["Elección de región",
                   "Debe verificarse que las tres familias de modelos estén "
                   "disponibles en la región seleccionada, dado que la cobertura "
                   "varía entre ellas.", "Bloqueante"],
                  ["Credenciales de acceso programático",
                   "Rol de IAM asociado al servicio de cómputo. Se desaconseja el "
                   "uso de claves estáticas de larga duración.", "Bloqueante"],
              ],
              anchos=[4.2, 9.4, 2.4])

        doc.add_heading("Alojamiento y ejecución", level=2)
        parrafo(doc,
                "La aplicación requiere un proceso persistente que mantenga una "
                "conexión abierta con cada navegador, por lo que no puede alojarse "
                "sobre plataformas de funciones efímeras. Esta restricción se "
                "verificó de forma empírica durante el desarrollo: un intento de "
                "despliegue sobre una plataforma de ese tipo resultó fallido, no por "
                "un defecto de configuración, sino por incompatibilidad entre el "
                "modelo de ejecución y el que la aplicación necesita.")
        tabla(doc,
              ["Requisito", "Detalle", "Carácter"],
              [
                  ["Servicio de cómputo con proceso persistente",
                   "Contenedor gestionado o instancia. Alternativamente, una "
                   "plataforma especializada en aplicaciones de datos para "
                   "despliegues de bajo volumen.", "Bloqueante"],
                  ["Intérprete de Python 3.11 o superior",
                   "Con las dependencias declaradas en requirements.txt.",
                   "Bloqueante"],
                  ["Certificado y cifrado en tránsito",
                   "Terminación TLS ante el servicio de cómputo. Bedrock ya impone "
                   "cifrado en sus propias comunicaciones.", "Alto"],
              ],
              anchos=[4.2, 9.4, 2.4])

        doc.add_heading("Persistencia de datos", level=2)
        parrafo(doc,
                "En la entrega actual la galería y el historial residen en memoria y "
                "se pierden al reiniciar. Un entorno productivo exige almacenamiento "
                "duradero, que además condiciona el cumplimiento de la política de "
                "conservación de noventa días recogida en la guía de marca.")
        tabla(doc,
              ["Requisito", "Detalle", "Carácter"],
              [
                  ["Base de datos para el historial de versiones",
                   "Almacén documental que preserve el carácter solo-anexado del "
                   "registro y admita bloqueo optimista por versión.", "Alto"],
                  ["Almacenamiento de objetos para las imágenes",
                   "Con los metadatos de procedencia asociados a cada pieza.",
                   "Alto"],
                  ["Índice vectorial persistente",
                   "El índice en memoria deja de ser suficiente cuando debe "
                   "compartirse entre procesos o sobrevivir a los reinicios.",
                   "Medio"],
                  ["Cifrado en reposo con claves gestionadas",
                   "Aplicable tanto al almacén de imágenes como al historial.",
                   "Alto"],
              ],
              anchos=[4.2, 9.4, 2.4])

        doc.add_heading("Identidad y control de acceso", level=2)
        tabla(doc,
              ["Requisito", "Detalle", "Carácter"],
              [
                  ["Proveedor de identidad",
                   "Servicio de autenticación gestionado o federación con el "
                   "sistema corporativo. El módulo de permisos ya está desacoplado "
                   "de la autenticación y no requeriría reescritura.", "Bloqueante"],
                  ["Política de mínimo privilegio",
                   "Permiso de invocación restringido a los identificadores de "
                   "modelo efectivamente utilizados, en lugar de acceso completo al "
                   "servicio.", "Alto"],
              ],
              anchos=[4.2, 9.4, 2.4])

        doc.add_heading("Control de coste y explotación", level=2)
        tabla(doc,
              ["Requisito", "Detalle", "Carácter"],
              [
                  ["Presupuesto con alertas",
                   "Umbrales de aviso sobre el gasto mensual. La facturación por "
                   "token generado hace que un uso descontrolado se traduzca "
                   "directamente en coste.", "Alto"],
                  ["Salvaguardas gestionadas del proveedor",
                   "Segunda capa de moderación con políticas de contenido y "
                   "detección de datos personales, complementaria a la implementada "
                   "en la aplicación.", "Alto"],
                  ["Registro y observabilidad",
                   "Trazas de invocación, latencias y consumo de tokens, así como "
                   "alarmas ante errores de acceso o limitación de tasa.", "Medio"],
                  ["Almacenamiento en caché de instrucciones",
                   "Las instrucciones de sistema son idénticas en todas las "
                   "invocaciones de una misma tarea, lo que permite reducir el coste "
                   "de entrada.", "Medio"],
                  ["Copia de seguridad y política de retención",
                   "Conservación durante noventa días y eliminación posterior, "
                   "conforme a la política recogida en la guía de marca.", "Medio"],
              ],
              anchos=[4.2, 9.4, 2.4])

        caja_destacada(
            doc,
            "Sobre el orden de ejecución",
            "Los requisitos marcados como bloqueantes constituyen la condición "
            "mínima para que la aplicación se ejecute contra los modelos reales, y "
            "pueden cubrirse en cuestión de horas. Los clasificados como de "
            "carácter alto son los que separan una demostración funcional de un "
            "servicio que la agencia pueda utilizar con datos de cliente. Conviene "
            "no confundir ambos niveles: la aplicación puede estar operativa mucho "
            "antes de estar preparada para producción.",
            "FFF4E5",
        )

    mover_antes(ancla, recolectar(doc, constructor))
    reemplazar_en_documento(doc, "7. Fuentes y herramientas", "8. Fuentes y herramientas")
    print("   · añadida sección 7 con cinco bloques de requisitos")
    print("   · renumerada la sección de fuentes como 8")


# ---------------------------------------------------------------------------
# 7 · Glosario
# ---------------------------------------------------------------------------

GLOSARIO: list[tuple[str, str]] = [
    ("Alucinación",
     "Afirmación falsa que un modelo de lenguaje presenta como cierta. No es un "
     "error de cálculo, sino consecuencia de que el modelo genera texto "
     "plausible sin verificar los hechos."),
    ("Amazon Bedrock",
     "Servicio de Amazon Web Services que ofrece acceso a modelos de "
     "inteligencia artificial de distintos fabricantes mediante una interfaz "
     "común, sin necesidad de administrar servidores."),
    ("API",
     "Interfaz de programación. Conjunto de operaciones que un servicio expone "
     "para que otros programas lo utilicen, junto con las reglas sobre cómo "
     "invocarlas."),
    ("boto3",
     "Biblioteca oficial que permite a un programa escrito en Python "
     "comunicarse con los servicios de Amazon Web Services."),
    ("Claude",
     "Familia de modelos de lenguaje desarrollada por Anthropic. En esta "
     "aplicación se emplea para todas las operaciones sobre texto."),
    ("Contrato del modelo",
     "Especificación de los campos que una petición debe incluir, con sus tipos "
     "y valores admisibles. Si la petición no lo cumple, el servicio la rechaza."),
    ("Difusión (modelo de)",
     "Tipo de modelo que genera imágenes partiendo de ruido aleatorio y "
     "refinándolo paso a paso hasta obtener una imagen coherente con la "
     "descripción recibida."),
    ("Doble de transporte",
     "Objeto que ocupa el lugar del cliente real de un servicio y expone sus "
     "mismas operaciones, permitiendo ejecutar la aplicación sin acceder a la "
     "red. En este trabajo, la clase MockBedrockRuntime."),
    ("Escala de guía (cfg_scale)",
     "Parámetro de la generación de imágenes que determina con qué fidelidad "
     "debe ceñirse el resultado a la descripción. Valores altos aumentan la "
     "adherencia; valores excesivos introducen artefactos."),
    ("Inferencia",
     "Ejecución de un modelo ya entrenado para obtener un resultado a partir de "
     "una entrada. Es la operación que se factura por uso."),
    ("Inyección de prompt",
     "Técnica por la que un usuario introduce, dentro del contenido que aporta, "
     "frases con forma de instrucción con el fin de alterar el comportamiento "
     "del modelo o extraer sus instrucciones de sistema."),
    ("JSON",
     "Formato de texto estructurado empleado para intercambiar datos entre "
     "programas. Es el formato en que viajan las peticiones y las respuestas de "
     "Amazon Bedrock."),
    ("max_tokens",
     "Límite superior de longitud de la respuesta. Actúa simultáneamente como "
     "control de calidad y de coste."),
    ("Memoria (en el sentido de esta memoria)",
     "Mecanismo que aporta continuidad al trabajo en curso: qué se está "
     "editando y por qué versiones ha pasado. No debe confundirse con la "
     "generación aumentada por recuperación."),
    ("Modelo fundacional",
     "Modelo de gran tamaño entrenado con datos muy diversos, que sirve de base "
     "para múltiples tareas sin necesidad de reentrenarlo."),
    ("Payload",
     "Cuerpo de una petición: el conjunto de datos que se envía al servicio, "
     "distinto de la información de encaminamiento y autenticación."),
    ("Producto mínimo viable",
     "Versión más reducida de una aplicación que ya aporta valor y demuestra "
     "que el planteamiento funciona."),
    ("Prompt",
     "Texto que se proporciona a un modelo para obtener una respuesta. En "
     "generación de imágenes, la descripción de la escena buscada."),
    ("Prompt negativo",
     "Descripción de aquello que no debe aparecer en la imagen. En Stable "
     "Diffusion se transmite como un segundo prompt con peso negativo."),
    ("RAG (generación aumentada por recuperación)",
     "Técnica que busca en documentos propios los fragmentos pertinentes para "
     "una consulta y se los entrega al modelo antes de que responda, de modo "
     "que su respuesta se apoye en conocimiento verificable."),
    ("Recall",
     "Proporción de los elementos relevantes que un sistema de búsqueda "
     "consigue recuperar. Un recall de cinco sobre ocho indica que se "
     "recuperaron cinco de los ocho fragmentos esperados."),
    ("Representación vectorial (embedding)",
     "Traducción de un texto a una lista de números que sitúa su significado en "
     "un espacio matemático, de manera que textos afines quedan próximos entre "
     "sí."),
    ("Semilla (seed)",
     "Número que determina el punto de partida aleatorio de la generación de "
     "una imagen. Fijarla permite reproducir exactamente el mismo resultado."),
    ("Similitud coseno",
     "Medida de proximidad entre dos representaciones vectoriales. Cuanto más "
     "próxima a uno, mayor afinidad de significado."),
    ("Solo-anexado",
     "Propiedad de un registro en el que solo se añaden entradas y nunca se "
     "modifican ni eliminan las existentes. Garantiza que el historial sea "
     "auditable."),
    ("Stable Diffusion",
     "Modelo de difusión desarrollado por Stability AI que genera imágenes a "
     "partir de descripciones textuales."),
    ("Streamlit",
     "Marco de trabajo de Python que permite construir interfaces web con poco "
     "código, habitual en la creación de prototipos de aplicaciones de datos."),
    ("System prompt (instrucciones de sistema)",
     "Texto que fija el comportamiento del modelo antes de que intervenga el "
     "usuario: su papel, su objetivo, sus restricciones y el formato de su "
     "respuesta."),
    ("Temperatura",
     "Parámetro que regula la variabilidad de la respuesta. Valores próximos a "
     "cero producen resultados casi deterministas; valores altos favorecen la "
     "diversidad."),
    ("Titan",
     "Familia de modelos de Amazon. En este trabajo se emplea su modelo de "
     "representaciones vectoriales para la recuperación de contexto."),
    ("Token",
     "Unidad mínima en que un modelo divide el texto. Equivale "
     "aproximadamente a una fracción de palabra y constituye la unidad de "
     "facturación."),
    ("Top-P",
     "Parámetro que restringe las opciones consideradas a las más probables "
     "hasta alcanzar una probabilidad acumulada determinada."),
    ("Trazabilidad",
     "Capacidad de reconstruir cómo se produjo un resultado: con qué modelo, "
     "con qué parámetros, a partir de qué entrada y por decisión de quién."),
    ("Umbral de similitud",
     "Valor mínimo de proximidad por debajo del cual un fragmento recuperado se "
     "descarta por considerarse irrelevante."),
    ("Wrapper",
     "Capa propia de la aplicación que envuelve al modelo: recibe la petición "
     "del usuario, aplica las reglas de negocio y de seguridad, invoca el "
     "modelo y procesa su respuesta."),
]


def añadir_glosario(doc) -> None:
    print("7. Glosario")

    if buscar_parrafo(doc, "Glosario de términos técnicos", estilo="Heading 1"):
        print("   · ya presente; se omite")
        return

    doc.add_page_break()
    doc.add_heading("9. Glosario de términos técnicos", level=1)
    parrafo(doc,
            "Se recogen los términos técnicos empleados en el documento, definidos "
            "en lenguaje accesible para lectores sin formación especializada. Las "
            "entradas se ordenan alfabéticamente.")

    filas = [[termino, definicion] for termino, definicion in GLOSARIO]
    tabla(doc, ["Término", "Definición"], filas, anchos=[4.4, 11.6])
    print(f"   · añadidas {len(GLOSARIO)} entradas")


# ---------------------------------------------------------------------------


def main() -> int:
    if not DOCUMENTO.exists():
        print(f"No se encuentra {DOCUMENTO}")
        return 1
    try:
        with open(DOCUMENTO, "r+b"):
            pass
    except PermissionError:
        print(f"El documento está abierto en Word: {DOCUMENTO.name}")
        print("Ciérralo y vuelve a ejecutar.")
        return 1

    doc = Document(str(DOCUMENTO))

    corregir_terminologia(doc)
    desarrollar_razonamiento_adaptativo(doc)
    aclarar_canonico(doc)
    añadir_aportaciones(doc)
    añadir_pilares_imagen(doc)
    añadir_produccion(doc)
    añadir_glosario(doc)

    doc.save(str(DOCUMENTO))
    print()
    print(f"Documento actualizado: {DOCUMENTO}")
    print("Recuerda actualizar el índice en Word: clic derecho sobre él, "
          "«Actualizar campos», «Actualizar toda la tabla».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
