"""Genera la memoria del tronco común en formato Word.

    python scripts/generar_memoria.py

La tabla de modelos y parámetros y el texto de las instrucciones de sistema se
leen del código fuente en lugar de transcribirse. De este modo el documento no
puede afirmar un valor de temperatura que la aplicación no aplique: toda
modificación de `src/bedrock/models.py` se propaga al documento en la siguiente
generación.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from docx import Document  # noqa: E402
from docx.enum.table import WD_TABLE_ALIGNMENT  # noqa: E402
from docx.enum.text import WD_ALIGN_PARAGRAPH  # noqa: E402
from docx.oxml import OxmlElement  # noqa: E402
from docx.oxml.ns import qn  # noqa: E402
from docx.shared import Cm, Pt, RGBColor  # noqa: E402

from src.bedrock.models import (  # noqa: E402
    IMAGE_STYLES,
    TEXT_PROFILES,
    TITAN_EMBEDDINGS,
    TextTask,
)
from src.config import ASSETS_DIR, DOCS_DIR  # noqa: E402
from src.prompts.system_prompts import build_system_prompt  # noqa: E402

AZUL = RGBColor(0x1B, 0x3A, 0x5C)
CORAL = RGBColor(0xF0, 0x55, 0x4F)
GRIS = RGBColor(0x5A, 0x62, 0x6B)
GRAFITO = RGBColor(0x23, 0x28, 0x2D)

AUTOR = "José Ruber Moncayo Navia"
TITULO = "Aplicación de generación de imágenes y edición de contenido con Amazon Bedrock"


# ---------------------------------------------------------------------------
# Utilidades de formato
# ---------------------------------------------------------------------------


def configurar_estilos(doc: Document) -> None:
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.15

    for nivel, tamano, color in [(1, 17, AZUL), (2, 14, AZUL), (3, 12, GRAFITO)]:
        estilo = doc.styles[f"Heading {nivel}"]
        estilo.font.name = "Calibri"
        estilo.font.size = Pt(tamano)
        estilo.font.color.rgb = color
        estilo.font.bold = True
        estilo.paragraph_format.space_before = Pt(16 if nivel == 1 else 12)
        estilo.paragraph_format.space_after = Pt(6)


def parrafo(doc, texto="", *, negrita=False, cursiva=False, tamano=11,
            color=None, alineacion=None, espacio_despues=None, sangria=None):
    p = doc.add_paragraph()
    run = p.add_run(texto)
    run.bold = negrita
    run.italic = cursiva
    run.font.size = Pt(tamano)
    if color is not None:
        run.font.color.rgb = color
    if alineacion is not None:
        p.alignment = alineacion
    if espacio_despues is not None:
        p.paragraph_format.space_after = Pt(espacio_despues)
    if sangria is not None:
        p.paragraph_format.left_indent = Cm(sangria)
    return p


def parrafo_rico(doc, fragmentos, *, sangria=None, espacio_despues=None):
    """Párrafo con tramos en negrita: fragmentos es [(texto, negrita), ...]."""
    p = doc.add_paragraph()
    for texto, negrita in fragmentos:
        run = p.add_run(texto)
        run.bold = negrita
        run.font.size = Pt(11)
    if sangria is not None:
        p.paragraph_format.left_indent = Cm(sangria)
    if espacio_despues is not None:
        p.paragraph_format.space_after = Pt(espacio_despues)
    return p


def vineta(doc, texto, nivel=0):
    p = doc.add_paragraph(texto, style="List Bullet")
    p.paragraph_format.left_indent = Cm(0.75 + nivel * 0.6)
    p.paragraph_format.space_after = Pt(4)
    return p


def vineta_rica(doc, fragmentos, nivel=0):
    p = doc.add_paragraph(style="List Bullet")
    for texto, negrita in fragmentos:
        run = p.add_run(texto)
        run.bold = negrita
        run.font.size = Pt(11)
    p.paragraph_format.left_indent = Cm(0.75 + nivel * 0.6)
    p.paragraph_format.space_after = Pt(4)
    return p


def sombrear(celda, hex_color: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), hex_color)
    celda._tc.get_or_add_tcPr().append(shd)


def tabla(doc, cabeceras: list[str], filas: list[list[str]],
          anchos: list[float] | None = None):
    t = doc.add_table(rows=1, cols=len(cabeceras))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER

    for i, texto in enumerate(cabeceras):
        celda = t.rows[0].cells[i]
        celda.text = ""
        run = celda.paragraphs[0].add_run(texto)
        run.bold = True
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        sombrear(celda, "1B3A5C")

    for fila in filas:
        celdas = t.add_row().cells
        for i, texto in enumerate(fila):
            celdas[i].text = ""
            run = celdas[i].paragraphs[0].add_run(str(texto))
            run.font.size = Pt(9.5)

    if anchos:
        for fila in t.rows:
            for i, ancho in enumerate(anchos):
                fila.cells[i].width = Cm(ancho)
    return t


def caja_destacada(doc, titulo: str, cuerpo: str, color_fondo="FFF4E5"):
    """Recuadro para decisiones y advertencias clave."""
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    celda = t.rows[0].cells[0]
    sombrear(celda, color_fondo)

    celda.text = ""
    p = celda.paragraphs[0]
    run = p.add_run(titulo)
    run.bold = True
    run.font.size = Pt(10)
    run.font.color.rgb = GRAFITO

    p2 = celda.add_paragraph()
    run2 = p2.add_run(cuerpo)
    run2.font.size = Pt(10)
    doc.add_paragraph()
    return t


def bloque_codigo(doc, texto: str, tamano=8.5):
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    celda = t.rows[0].cells[0]
    sombrear(celda, "F5F5F2")
    celda.text = ""
    for i, linea in enumerate(texto.split("\n")):
        p = celda.paragraphs[0] if i == 0 else celda.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        run = p.add_run(linea)
        run.font.name = "Consolas"
        run.font.size = Pt(tamano)
    doc.add_paragraph()
    return t


def indice(doc):
    """Inserta un campo TOC que Word rellena al abrir el documento."""
    p = doc.add_paragraph()
    run = p.add_run()

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = r'TOC \o "1-2" \h \z \u'
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    texto = OxmlElement("w:t")
    texto.text = ("Para generar el índice: clic derecho sobre esta línea y "
                  "seleccionar «Actualizar campos».")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")

    for elemento in (fld_begin, instr, fld_sep, texto, fld_end):
        run._r.append(elemento)


def pie_de_pagina(doc) -> None:
    seccion = doc.sections[0]
    p = seccion.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f"{AUTOR} · Caso Práctico Unidad 3 · Generative AI · IEP    ")
    run.font.size = Pt(8)
    run.font.color.rgb = GRIS

    run2 = p.add_run()
    for tipo, texto in [("begin", None), (None, "PAGE"), ("separate", None),
                        (None, "1"), ("end", None)]:
        if tipo:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), tipo)
            run2._r.append(fld)
        elif texto == "PAGE":
            instr = OxmlElement("w:instrText")
            instr.text = "PAGE"
            run2._r.append(instr)
        else:
            t = OxmlElement("w:t")
            t.text = texto
            run2._r.append(t)
    run2.font.size = Pt(8)
    run2.font.color.rgb = GRIS


# ---------------------------------------------------------------------------
# Secciones del documento
# ---------------------------------------------------------------------------


def portada(doc):
    for _ in range(4):
        doc.add_paragraph()

    parrafo(doc, "INSTITUTO EUROPEO DE POSGRADO", negrita=True, tamano=12,
            color=GRIS, alineacion=WD_ALIGN_PARAGRAPH.CENTER)
    parrafo(doc, "Máster en Inteligencia Artificial Generativa", tamano=11,
            color=GRIS, alineacion=WD_ALIGN_PARAGRAPH.CENTER,
            espacio_despues=40)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(TITULO)
    run.bold = True
    run.font.size = Pt(22)
    run.font.color.rgb = AZUL
    p.paragraph_format.space_after = Pt(10)

    parrafo(doc, "Caso Práctico · Unidad 3 · Generative AI", tamano=13,
            color=GRAFITO, alineacion=WD_ALIGN_PARAGRAPH.CENTER,
            espacio_despues=6)
    parrafo(doc, "Vía A — Aplicación funcional", negrita=True, tamano=12,
            color=CORAL, alineacion=WD_ALIGN_PARAGRAPH.CENTER,
            espacio_despues=50)

    parrafo(doc, "Autor", negrita=True, tamano=10, color=GRIS,
            alineacion=WD_ALIGN_PARAGRAPH.CENTER, espacio_despues=2)
    parrafo(doc, AUTOR, negrita=True, tamano=14,
            alineacion=WD_ALIGN_PARAGRAPH.CENTER, espacio_despues=24)

    parrafo(doc, "Aplicación desarrollada:  Aurora Studio", tamano=10, color=GRIS,
            alineacion=WD_ALIGN_PARAGRAPH.CENTER, espacio_despues=2)
    parrafo(doc, "Modo de ejecución:  simulado (sin cuenta de Amazon Web Services)",
            tamano=10, color=GRIS, alineacion=WD_ALIGN_PARAGRAPH.CENTER)

    doc.add_page_break()


def seccion_indice(doc):
    doc.add_heading("Índice", level=1)
    indice(doc)
    doc.add_page_break()


def seccion_1(doc):
    doc.add_heading("Introducción y alcance", level=1)

    parrafo(doc,
            "El presente documento expone el diseño y la implementación de Aurora "
            "Studio, una herramienta interna de generación de imágenes y edición de "
            "contenido concebida para una agencia de marketing y publicidad, "
            "construida sobre Amazon Bedrock. Se desarrollan las seis secciones del "
            "tronco común establecidas en la guía del trabajo práctico (apartados 3.1 "
            "a 3.6) y se documenta la ejecución de la Vía A, correspondiente a la "
            "aplicación funcional que acompaña a esta memoria.")

    parrafo(doc,
            "La solución cubre las cuatro funcionalidades requeridas en el enunciado: "
            "generación de imágenes a partir de descripciones textuales con selección "
            "de estilo y galería de resultados; edición de contenido mediante cuatro "
            "operaciones diferenciadas con historial de versiones; colaboración "
            "multiusuario con roles, permisos y comentarios; y un marco de ética y "
            "seguridad implementado en el propio flujo de ejecución.")

    parrafo(doc,
            "La estructura del documento responde al orden establecido en la guía. "
            "Tras esta introducción se desarrolla el tronco común, se detalla la "
            "ejecución de la vía elegida, se enumeran las limitaciones identificadas y "
            "se incluye una autoevaluación frente a los criterios de la rúbrica.")

    doc.add_heading("Consideración preliminar sobre el modo de ejecución", level=2)

    parrafo(doc,
            "La aplicación se entrega ejecutándose en modo simulado. No se ha "
            "contratado una cuenta de Amazon Web Services y, en consecuencia, ninguna "
            "de las respuestas que muestra la interfaz procede de los modelos alojados "
            "en Amazon Bedrock. La guía del trabajo práctico contempla expresamente "
            "esta posibilidad y no la penaliza, si bien exige que la integración esté "
            "correctamente planteada. Dicha exigencia ha condicionado la decisión "
            "arquitectónica principal del proyecto, que se justifica en el apartado "
            "3.2.")

    caja_destacada(
        doc,
        "Síntesis",
        "El código responsable de construir las peticiones a Amazon Bedrock, "
        "enviarlas y procesar sus respuestas es código de producción y se ejecuta en "
        "su totalidad. La sustitución afecta exclusivamente al transporte de red. La "
        "modificación de la variable de entorno BEDROCK_BACKEND, de «mock» a «aws», "
        "habilita las llamadas reales sin requerir cambio alguno en el resto del "
        "código.",
        "E8F4EC",
    )


def seccion_31(doc):
    doc.add_heading("3.1. Problema y usuarios", level=1)

    parrafo(doc,
            "La agencia produce piezas creativas —entendidas como la combinación de "
            "una imagen y un texto— destinadas a campañas de cliente. El principal "
            "obstáculo identificado no reside en la capacidad técnica del equipo, sino "
            "en el número de iteraciones que atraviesa cada pieza antes de su "
            "publicación. El diseñador requiere propuestas visuales con las que "
            "articular la conversación con el cliente; el redactor reescribe un mismo "
            "texto en múltiples ocasiones; y el aprobador recibe sucesivas versiones "
            "por correo electrónico sin disponer de un mecanismo que le permita "
            "identificar las diferencias respecto a la versión anterior.")

    parrafo(doc,
            "Aurora Studio aborda simultáneamente las tres fricciones descritas: "
            "acelera la exploración visual, asiste el proceso de reescritura y "
            "preserva la trazabilidad de las operaciones realizadas.")

    doc.add_heading("Historias de usuario", level=2)

    parrafo(doc,
            "Se formulan a continuación las historias de usuario que definen los "
            "requisitos funcionales de la solución, siguiendo la estructura "
            "«Como [rol], quiero [acción], para [beneficio]».")

    historias = [
        ("Diseñador",
         "generar imágenes a partir de una descripción textual y seleccionar el estilo",
         "acelerar la elaboración de propuestas visuales sin depender de una sesión "
         "fotográfica"),
        ("Diseñador",
         "reproducir con exactitud una imagen generada previamente mediante su semilla",
         "iterar sobre una propuesta concreta en lugar de reiniciar el proceso"),
        ("Redactor",
         "resumir, expandir, corregir y generar variaciones de un texto",
         "reducir el tiempo de publicación y mejorar la consistencia estilística"),
        ("Redactor",
         "que la herramienta aplique automáticamente la guía de estilo de marca",
         "evitar la dependencia de la memoria en la aplicación de las normas "
         "editoriales"),
        ("Aprobador",
         "revisar, comparar y comentar versiones antes de la publicación",
         "controlar la calidad e identificar con precisión los cambios introducidos"),
        ("Aprobador",
         "restaurar una versión anterior sin pérdida del historial",
         "rectificar decisiones preservando la evidencia de lo aprobado"),
        ("Responsable legal",
         "conocer el prompt y la semilla de cualquier imagen publicada",
         "acreditar el proceso de generación ante una eventual reclamación de "
         "terceros"),
    ]

    for rol, accion, beneficio in historias:
        p = doc.add_paragraph(style="List Bullet")
        p.paragraph_format.left_indent = Cm(0.75)
        p.paragraph_format.space_after = Pt(6)
        for texto, negrita in [("Como ", False), (rol, True), (", quiero ", False),
                               (accion, True), (", para ", False),
                               (beneficio + ".", False)]:
            run = p.add_run(texto)
            run.bold = negrita
            run.font.size = Pt(11)

    doc.add_heading("Justificación de la cuarta figura de usuario", level=2)

    parrafo(doc,
            "Las tres primeras figuras —diseñador, redactor y aprobador— son las "
            "establecidas en el enunciado del caso. Se ha incorporado una cuarta "
            "figura, el responsable legal, por una razón de coherencia interna del "
            "diseño: es el actor que impone los requisitos de trazabilidad, "
            "conservación de la procedencia y cumplimiento en materia de derechos de "
            "autor que estructuran el apartado 3.6.")

    parrafo(doc,
            "La omisión de esta figura habría dejado dichos controles sin un usuario "
            "que los demandara y, por consiguiente, sin justificación funcional. En la "
            "práctica profesional, los requisitos de cumplimiento normativo raramente "
            "proceden de los perfiles productivos, sino de una función de control "
            "diferenciada. Su inclusión no amplía el alcance funcional de la "
            "aplicación, sino que fundamenta requisitos que el enunciado exige abordar "
            "en su apartado de consideraciones éticas y de seguridad.")


def seccion_32(doc):
    doc.add_heading("3.2. Arquitectura del sistema", level=1)

    parrafo(doc,
            "El sistema se estructura en cinco capas. El elemento central de la "
            "arquitectura es el wrapper, entendido como la capa propia de la "
            "aplicación que recibe la petición del usuario, aplica las reglas de "
            "negocio y de seguridad, determina qué modelo debe invocarse y con qué "
            "parámetros, realiza la llamada a Amazon Bedrock y procesa la respuesta "
            "antes de devolverla a la interfaz.")

    diagrama = ASSETS_DIR / "arquitectura.png"
    if diagrama.exists():
        doc.add_picture(str(diagrama), width=Cm(16.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        parrafo(doc, "Figura 1. Arquitectura del sistema Aurora Studio.", tamano=9,
                color=GRIS, alineacion=WD_ALIGN_PARAGRAPH.CENTER)

    doc.add_heading("Responsabilidad de cada capa", level=2)

    tabla(doc,
          ["Capa", "Responsabilidad", "Implementación"],
          [
              ["Interfaz",
               "Cuatro pantallas: generación de imágenes, edición de contenido, "
               "colaboración y galería.",
               "Streamlit · src/ui/"],
              ["Wrapper",
               "Moderación, defensa frente a inyección de prompt, construcción de "
               "instrucciones, recuperación de contexto, perfiles de inferencia y "
               "lógica de dominio.",
               "src/services/, src/security/, src/prompts/, src/domain/"],
              ["Transporte",
               "Serialización del cuerpo de la petición, invocación de invoke_model y "
               "análisis de la respuesta. Traducción de los errores del proveedor a "
               "mensajes accionables.",
               "src/bedrock/client.py"],
              ["Modelos",
               "Claude, Stable Diffusion XL y Titan Embeddings.",
               "Amazon Bedrock"],
              ["Almacenamiento",
               "Galería con metadatos de procedencia, historial de versiones de tipo "
               "solo-anexado e índice vectorial de la guía de marca.",
               "Estado de sesión · data/"],
          ],
          anchos=[2.6, 8.0, 5.4])

    doc.add_heading("Justificación de la API gestionada frente al despliegue propio",
                    level=2)

    parrafo(doc,
            "La alternativa a Amazon Bedrock consistiría en desplegar Stable Diffusion "
            "y un modelo de lenguaje de código abierto sobre infraestructura propia. "
            "Dicha alternativa se ha descartado atendiendo a tres criterios, ordenados "
            "según su peso en la decisión.")

    vineta_rica(doc, [
        ("Tiempo de puesta en marcha. ", True),
        ("Mediante Amazon Bedrock, la primera invocación resulta operativa el mismo "
         "día en que se concede el acceso a los modelos. Un despliegue propio "
         "requeriría aprovisionar instancias con unidades de procesamiento gráfico, "
         "instalar los pesos de los modelos, configurar el servicio de inferencia y "
         "resolver el escalado. Tratándose de una herramienta interna cuyo valor "
         "reside en el flujo de trabajo y no en la inferencia, dicho esfuerzo no "
         "resulta amortizable.", False),
    ])
    vineta_rica(doc, [
        ("Coste operativo. ", True),
        ("El modelo de facturación por uso se ajusta a un patrón de demanda irregular, "
         "caracterizado por picos coincidentes con los cierres de campaña y periodos "
         "de actividad reducida. Una unidad de procesamiento gráfico reservada genera "
         "coste con independencia de su utilización efectiva. Adicionalmente, la "
         "agencia no dispone de un equipo de plataforma que asuma el mantenimiento de "
         "dicho despliegue.", False),
    ])
    vineta_rica(doc, [
        ("Acceso unificado a múltiples modelos. ", True),
        ("El caso requiere tres familias de modelos —lenguaje, difusión y "
         "representaciones vectoriales— procedentes de tres proveedores distintos. "
         "Amazon Bedrock las expone a través de una interfaz única y un mecanismo "
         "común de gestión de credenciales.", False),
    ])

    parrafo(doc,
            "Las contrapartidas de esta decisión se asumen de forma explícita: "
            "dependencia de un proveedor único, menor control sobre las versiones de "
            "los modelos y crecimiento del coste marginal ante un incremento "
            "sostenido del volumen. Cabe identificar asimismo las condiciones bajo las "
            "cuales convendría reconsiderar la decisión: un volumen sostenido y "
            "predecible que permitiera amortizar infraestructura reservada, o un "
            "requisito regulatorio que impidiera la salida del contenido de la "
            "infraestructura propia.")

    doc.add_heading("Decisión estructural: la frontera de simulación", level=2)

    parrafo(doc,
            "La ausencia de una cuenta de Amazon Web Services obligaba a determinar en "
            "qué punto del sistema debía sustituirse la llamada real. La opción más "
            "inmediata —una bifurcación condicional en la lógica de negocio— fue "
            "descartada por cuanto deja el código de integración sin ejercitar: se "
            "escribe, pero no se verifica la corrección de su forma.")

    parrafo(doc,
            "La solución adoptada sustituye el objeto de transporte y no la lógica de "
            "la aplicación. La clase MockBedrockRuntime expone la misma operación "
            "invoke_model que el cliente de boto3, recibe el mismo cuerpo en formato "
            "JSON que se enviaría al proveedor y devuelve una respuesta con idéntica "
            "estructura. En consecuencia, la totalidad del código de la aplicación es "
            "código de producción: construye las peticiones reales, las serializa del "
            "mismo modo y analiza las respuestas siguiendo el mismo camino de "
            "ejecución.")

    caja_destacada(
        doc,
        "Consecuencia verificable",
        "El sustituto valida cada petición recibida frente al contrato documentado del "
        "modelo correspondiente y rechaza aquellas mal formadas del mismo modo que lo "
        "haría el proveedor: valor incorrecto en anthropic_version, temperatura fuera "
        "del intervalo [0, 1], escala de guía fuera de rango o conjunto de prompts "
        "vacío. Una petición incorrectamente construida falla durante el desarrollo en "
        "lugar de devolver una respuesta verosímil que enmascare el error. El conjunto "
        "de pruebas tests/test_contratos_bedrock.py verifica dichas validaciones.",
        "E8F0F8",
    )


def seccion_33(doc):
    doc.add_heading("3.3. Modelos y parámetros de inferencia", level=1)

    parrafo(doc,
            "Cada tarea emplea el modelo y los parámetros correspondientes a su "
            "naturaleza, conforme al principio establecido en la unidad: las tareas "
            "que exigen rigor y consistencia requieren temperaturas bajas, mientras "
            "que aquellas orientadas a la creatividad y la diversidad admiten "
            "temperaturas altas. La tabla siguiente se genera automáticamente a partir "
            "del módulo src/bedrock/models.py, de modo que refleja con exactitud los "
            "valores que la aplicación aplica en tiempo de ejecución.")

    doc.add_heading("Operaciones de texto (Claude)", level=2)

    filas = []
    orden = [TextTask.CORREGIR, TextTask.RESUMIR, TextTask.EXPANDIR, TextTask.VARIAR]
    for tarea in orden:
        p = TEXT_PROFILES[tarea]
        filas.append([
            tarea.etiqueta,
            p.model_id.replace("anthropic.", ""),
            f"{p.temperature}",
            f"{p.top_p}",
            f"{p.max_tokens}",
        ])
    tabla(doc, ["Tarea", "Modelo", "Temp.", "Top-P", "Máx. tokens"], filas,
          anchos=[4.4, 4.6, 1.9, 1.9, 3.2])

    parrafo(doc, "Justificación de cada configuración:", negrita=True)
    for tarea in orden:
        p = TEXT_PROFILES[tarea]
        parrafo_rico(doc, [(f"{tarea.etiqueta}. ", True), (p.justificacion, False)],
                     sangria=0.5, espacio_despues=6)

    doc.add_heading("Criterio de selección de la familia de modelos", level=2)

    parrafo(doc,
            "Se emplea Claude Haiku 4.5 para las tareas deterministas y de alto "
            "volumen, y Claude Sonnet 4.6 para aquellas de naturaleza creativa. La "
            "decisión de no adoptar los modelos más recientes de la familia Opus "
            "obedece a un criterio técnico que conviene explicitar: dichos modelos "
            "sustituyen el muestreo estadístico explícito por un mecanismo de "
            "razonamiento adaptativo gobernado por un parámetro de esfuerzo, y "
            "rechazan el parámetro de temperatura. Su adopción habría impedido "
            "demostrar el control de los parámetros de inferencia que constituye el "
            "objeto de estudio de esta unidad.")

    parrafo(doc,
            "Procede señalar la implicación de fondo que se deriva de lo anterior: el "
            "control de la generación está desplazándose desde el muestreo "
            "estadístico —temperatura y Top-P— hacia el control del proceso de "
            "razonamiento del modelo. Todo diseño formulado hoy sobre parámetros de "
            "muestreo debería prever dicha transición.")

    doc.add_heading("Generación de imágenes (Stable Diffusion XL)", level=2)

    parrafo(doc,
            "En el ámbito de la generación de imágenes los parámetros relevantes no "
            "son la temperatura y Top-P, sino la escala de guía (cfg_scale), el número "
            "de pasos de difusión (steps) y la semilla (seed). Cada estilo combina dos "
            "mecanismos: el preajuste nativo del modelo y un sufijo añadido al prompt. "
            "Dicha combinación responde a que los preajustes disponibles no cubren la "
            "totalidad de los estilos requeridos en el enunciado, dado que no existe "
            "un preajuste específico para la pintura al óleo.")

    filas_img = [
        [e.etiqueta, e.style_preset, f"{e.cfg_scale}", f"{e.steps}"]
        for e in IMAGE_STYLES.values()
    ]
    tabla(doc, ["Estilo", "style_preset", "cfg_scale", "steps"], filas_img,
          anchos=[5.0, 4.6, 3.2, 3.2])

    for estilo in IMAGE_STYLES.values():
        parrafo_rico(doc, [(f"{estilo.etiqueta}. ", True), (estilo.justificacion, False)],
                     sangria=0.5, espacio_despues=6)

    caja_destacada(
        doc,
        "La semilla como parámetro de auditabilidad",
        "Ante una misma semilla y un mismo prompt, Stable Diffusion produce la misma "
        "imagen. Esta propiedad convierte la generación en un proceso reproducible: "
        "permite al diseñador iterar sobre una propuesta concreta y faculta a la "
        "agencia para acreditar el procedimiento de obtención de una imagen "
        "publicada. Por este motivo la semilla se conserva junto a cada pieza de la "
        "galería y no se trata como un detalle de implementación interno.",
        "FFF4E5",
    )

    doc.add_heading("Representaciones vectoriales (Amazon Titan)", level=2)
    parrafo_rico(doc, [
        ("Modelo empleado: ", True), (f"{TITAN_EMBEDDINGS}. ", False),
        ("Se solicitan vectores de 1024 dimensiones normalizados. La normalización se "
         "delega en el modelo por cuanto permite calcular la similitud coseno como un "
         "producto escalar, evitando la división por las normas en cada consulta.",
         False),
    ])

    doc.add_heading("Control de coste y de longitud de respuesta", level=2)
    parrafo(doc,
            "El parámetro max_tokens se establece por tarea y no de forma global: 1024 "
            "para la operación de resumen, dado que un resultado de mayor extensión "
            "dejaría de cumplir su función, y 4096 para la expansión de ideas. "
            "Constituye simultáneamente un control de calidad y un mecanismo de "
            "contención del gasto, por cuanto la facturación de Amazon Bedrock se "
            "establece por token generado. En un entorno productivo procedería añadir "
            "un presupuesto mensual con alertas asociadas, así como el "
            "almacenamiento en caché de las instrucciones de sistema, idénticas en "
            "todas las invocaciones de una misma tarea.")


def seccion_34(doc):
    doc.add_heading("3.4. Instrucciones del sistema (System Prompt)", level=1)

    parrafo(doc,
            "Las instrucciones de sistema se construyen mediante composición y no como "
            "cuatro textos independientes: un tronco común e invariable —que "
            "comprende el rol, las restricciones y las reglas de prioridad— al que se "
            "añade un bloque específico por operación con su objetivo y su formato de "
            "salida. La justificación de este enfoque es de orden securitario: si cada "
            "operación replicara sus propias reglas, estas divergirían con el tiempo y "
            "la defensa frente a la inyección de prompt presentaría vulnerabilidades "
            "distintas según la operación seleccionada por el usuario.")

    doc.add_heading("Los cuatro pilares", level=2)

    tabla(doc,
          ["Pilar", "Contenido en Aurora Studio"],
          [
              ["Rol / persona",
               "Asistente editorial interno de una agencia de marketing, caracterizado "
               "como editor profesional de marca: preciso, sobrio y directo, con "
               "prioridad de la claridad sobre el efecto estilístico."],
              ["Objetivo",
               "Específico por operación: reducción al 30–40 % de la extensión "
               "original en el resumen, desarrollo sin introducción de hechos nuevos "
               "en la expansión, corrección sin reescritura por preferencia, y "
               "generación de tres variaciones genuinamente diferenciadas."],
              ["Restricciones",
               "Siete reglas inquebrantables: no inventar datos, advertir ante la "
               "ausencia de información, respetar el idioma de entrada, conservar el "
               "significado, no emitir afirmaciones sensibles sin respaldo, no "
               "reproducir marcas ajenas y no producir estereotipos. A ellas se añaden "
               "las reglas de prioridad frente a la inyección de instrucciones."],
              ["Formato de salida",
               "Definido por operación: texto plano sin preámbulos para el resumen; "
               "párrafos con un máximo de tres secciones para la expansión; texto "
               "corregido acompañado de una sección de cambios para la corrección; y "
               "tres bloques etiquetados en formato Markdown para las variaciones."],
          ],
          anchos=[3.4, 12.6])

    doc.add_heading("Instrucciones completas (operación de corrección)", level=2)

    parrafo(doc,
            "Se reproducen íntegramente las instrucciones que la aplicación transmite "
            "al modelo, extraídas directamente del código fuente. El bloque de "
            "contexto de marca que incorpora el mecanismo de recuperación se detalla "
            "en el apartado 3.5.")

    prompt = build_system_prompt(TextTask.CORREGIR)
    bloque_codigo(doc, prompt, tamano=7.8)

    doc.add_heading("Mecanismo de prioridad de instrucciones", level=2)

    parrafo(doc,
            "El apartado denominado «Prioridad de instrucciones» constituye el "
            "elemento que convierte la delimitación del contenido en una defensa "
            "efectiva. Establece de forma explícita que el material comprendido entre "
            "las etiquetas de contenido tiene naturaleza de dato y en ningún caso de "
            "instrucción, enumera los patrones de ataque más frecuentes para que el "
            "modelo los reconozca como texto susceptible de edición, y determina que "
            "las reglas de sistema prevalecen sobre cualquier contenido aportado por "
            "el usuario.")

    parrafo(doc,
            "Esta medida resulta insuficiente por sí sola: un usuario podría cerrar la "
            "etiqueta delimitadora e intentar redactar fuera del bloque acotado. Dicho "
            "vector se neutraliza mediante código y no mediante instrucciones, según "
            "se detalla en el apartado 3.6.")


def seccion_35(doc):
    doc.add_heading("3.5. RAG y memoria", level=1)

    caja_destacada(
        doc,
        "Delimitación conceptual",
        "La generación aumentada por recuperación aporta conocimiento verificable; la "
        "memoria aporta continuidad del trabajo en curso. Aurora Studio implementa "
        "ambos mecanismos y los mantiene deliberadamente diferenciados.",
        "E8F4EC",
    )

    doc.add_heading("Justificación del uso de RAG", level=2)

    parrafo(doc,
            "La aplicación requiere que el modelo de lenguaje disponga de la guía de "
            "estilo interna, que comprende la paleta cromática, la terminología de "
            "producto, las prohibiciones estilísticas y la política legal. Dicho "
            "conocimiento no puede incorporarse a las instrucciones de sistema por "
            "tres razones: ocuparía varios miles de tokens en cada invocación, "
            "quedaría desactualizado ante cada modificación normativa del departamento "
            "jurídico, y no permitiría citar la fuente concreta que respalda una "
            "recomendación determinada.")

    parrafo(doc,
            "Se trata, por tanto, del caso de uso canónico de la generación aumentada "
            "por recuperación: obtener de un corpus propio los fragmentos pertinentes "
            "para la consulta formulada y proporcionárselos al modelo con carácter "
            "previo a la generación de la respuesta.")

    doc.add_heading("Construcción del índice", level=2)

    bloque_codigo(doc,
                  "4 documentos .md de la guia de marca\n"
                  "        |\n"
                  "        v  troceado por secciones (encabezados de nivel 2)\n"
                  "14 fragmentos\n"
                  "        |\n"
                  "        v  Amazon Titan Embeddings - 1024 dimensiones\n"
                  "matriz 14 x 1024\n"
                  "        |\n"
                  "consulta --> embedding --> similitud coseno --> top-3 con umbral",
                  tamano=9)

    parrafo(doc, "Tres decisiones de diseño requieren justificación expresa.")

    vineta_rica(doc, [
        ("Segmentación por secciones frente a ventana de caracteres. ", True),
        ("La guía de estilo presenta una estructura temática propia. Su segmentación "
         "cada N caracteres fragmentaría las tablas y separaría cada prohibición de su "
         "contexto. Cuando el documento posee estructura propia, la segmentación debe "
         "respetarla.", False),
    ])
    vineta_rica(doc, [
        ("Índice en memoria frente a base de datos vectorial gestionada. ", True),
        ("El corpus está compuesto por catorce fragmentos. La incorporación de "
         "soluciones como OpenSearch Serverless o pgvector constituiría "
         "sobreingeniería. El umbral a partir del cual dicha migración resultaría "
         "justificada se sitúa en el orden de las decenas de miles de fragmentos, o "
         "bien cuando el índice deba compartirse entre procesos y persistir entre "
         "reinicios.", False),
    ])
    vineta_rica(doc, [
        ("Umbral de similitud calibrado empíricamente. ", True),
        ("Se midió la puntuación del fragmento mejor valorado sobre dos poblaciones de "
         "consultas: ocho consultas legítimas relativas a la guía de marca y cuatro "
         "consultas de ruido ajenas al dominio. Las consultas de ruido no superaron el "
         "valor 0,052, mientras que la consulta legítima peor valorada alcanzó 0,120. "
         "El umbral se estableció en 0,09, situado en el intervalo entre ambas "
         "poblaciones. El procedimiento es reproducible mediante el script "
         "tests/test_rag_umbral.py.", False),
    ])

    parrafo(doc,
            "El establecimiento de un umbral previene el error más frecuente en una "
            "implementación deficientemente calibrada: la entrega sistemática de k "
            "fragmentos con independencia de su pertinencia. La incorporación de "
            "contexto irrelevante resulta más perjudicial que su ausencia, por cuanto "
            "induce al modelo a establecer relaciones inexistentes.")

    doc.add_heading("Justificación del uso de memoria", level=2)

    parrafo(doc,
            "La memoria de Aurora Studio se materializa en el historial de la pieza en "
            "curso: el texto sometido a edición, sus versiones precedentes, la autoría "
            "de cada modificación con indicación del modelo y los parámetros "
            "empleados, y los comentarios asociados. Su función es aportar continuidad "
            "dentro de la sesión de trabajo.")

    parrafo(doc,
            "Su implementación adopta la forma de un registro de solo-anexado: las "
            "versiones no se sobrescriben en ningún caso, y la restauración de una "
            "versión anterior genera una versión nueva en lugar de eliminar las "
            "existentes. Esta decisión implica un mayor consumo de memoria y se "
            "considera no obstante la correcta, por cuanto en un flujo de aprobación "
            "la capacidad de acreditar qué se aprobó y en qué momento constituye un "
            "requisito de trazabilidad y no una comodidad funcional.")

    doc.add_heading("Diferenciación entre ambos mecanismos", level=2)

    tabla(doc,
          ["Criterio", "RAG", "Memoria"],
          [
              ["Naturaleza de la aportación", "Conocimiento verificable y externo",
               "Continuidad del trabajo en curso"],
              ["Origen", "Guía de estilo de marca (documentos propios)",
               "Acciones del usuario durante la sesión"],
              ["Mecanismo de acceso", "Similitud semántica sobre representaciones "
               "vectoriales",
               "Acceso directo al historial de la pieza"],
              ["Frecuencia de cambio", "Ante actualizaciones de la guía por marca o "
               "asesoría jurídica",
               "En cada operación que el usuario consolida"],
              ["Ubicación en el código", "src/services/rag_service.py",
               "src/domain/versioning.py"],
          ],
          anchos=[3.6, 6.2, 6.2])

    parrafo(doc,
            "Se ha evitado deliberadamente el error consistente en emplear la memoria "
            "conversacional como sustituto de la recuperación, esto es, incorporar la "
            "guía de estilo al primer mensaje de la conversación confiando en su "
            "retención por parte del modelo. Dicha práctica consume contexto en cada "
            "turno, degrada la atención sobre la información relevante e imposibilita "
            "determinar qué fragmento concreto respaldó una recomendación.")


def seccion_36(doc):
    doc.add_heading("3.6. Ética y seguridad", level=1)

    parrafo(doc,
            "Los cuatro frentes establecidos en la guía se abordan mediante controles "
            "implementados en el flujo de ejecución y no únicamente enunciados. Se "
            "documenta asimismo, en cada uno de ellos, el alcance efectivo del control "
            "y los elementos que resultarían necesarios en un entorno productivo.")

    doc.add_heading("Moderación de contenido", level=2)

    parrafo(doc,
            "Se somete a moderación tanto la entrada como la salida. La moderación "
            "exclusiva de la entrada resulta insuficiente, por cuanto una petición "
            "inocua puede generar una respuesta problemática. La secuencia de pasos se "
            "ha ordenado de modo que los controles de menor coste computacional "
            "precedan a los de mayor coste.")

    bloque_codigo(doc,
                  "1. Moderar la entrada        <- si bloquea, no se invoca al modelo\n"
                  "2. Sanear anti-inyeccion     <- previo a la construccion del prompt\n"
                  "3. Recuperar contexto (RAG)\n"
                  "4. Construir las instrucciones\n"
                  "5. Invocar el modelo\n"
                  "6. Moderar la salida         <- el riesgo no reside solo en la entrada",
                  tamano=9)

    parrafo(doc,
            "La moderación implementada opera mediante listas y reglas, por lo que "
            "detecta las infracciones evidentes y no aquellas de carácter sutil. Se "
            "declara esta limitación de forma explícita por cuanto su presentación "
            "como solución completa constituiría precisamente el error que el caso "
            "requiere evitar. En una implantación real conformaría la primera de tres "
            "capas, complementada por Amazon Bedrock Guardrails —con políticas "
            "gestionadas de contenido y detección de información personal— y por los "
            "filtros nativos de los propios modelos. Cabe señalar que Stable Diffusion "
            "devuelve el indicador CONTENT_FILTERED al rechazar una generación, "
            "circunstancia que la aplicación contempla y gestiona.")

    doc.add_heading("Inyección de prompt", level=2)

    parrafo(doc,
            "El modelo de amenaza considerado corresponde a un usuario autenticado de "
            "la herramienta: un redactor, o bien una persona que incorpora un texto de "
            "origen externo sin revisión previa. Su finalidad puede consistir en "
            "extraer las instrucciones de sistema, anular las reglas de marca o "
            "emplear la herramienta al margen de la política establecida.")

    parrafo(doc,
            "La defensa se articula en tres capas, de las cuales únicamente una ofrece "
            "garantía determinista.")

    tabla(doc,
          ["Capa", "Funcionamiento", "Garantía"],
          [
              ["Neutralización de delimitadores",
               "Sustituye toda aparición de las etiquetas reservadas en el texto "
               "aportado por el usuario, impidiendo el cierre del bloque de contenido.",
               "Determinista"],
              ["Detección de patrones",
               "Identifica formulaciones con estructura de instrucción y notifica al "
               "usuario y al registro de la aplicación.",
               "Heurística"],
              ["Prioridad declarada en las instrucciones",
               "Las instrucciones de sistema establecen la naturaleza de dato del "
               "contenido delimitado y la prevalencia de las reglas de sistema.",
               "Dependiente del modelo"],
          ],
          anchos=[4.4, 8.6, 3.0])

    caja_destacada(
        doc,
        "Criterio adoptado ante entradas sospechosas",
        "La entrada sospechosa no se rechaza, sino que se neutraliza y se notifica. El "
        "rechazo constituiría una respuesta inadecuada, por cuanto un redactor puede "
        "legítimamente requerir la edición de un texto que trate sobre inyección de "
        "prompt, y la herramienta debe permitirlo. Lo que no debe permitir es que "
        "dicho texto altere el comportamiento del modelo.",
        "FFF4E5",
    )

    parrafo(doc,
            "Como control de última instancia, la moderación de salida verifica que la "
            "respuesta no contenga fragmentos de las propias instrucciones de sistema. "
            "Su presencia constituiría el indicio de una inyección exitosa, ante lo "
            "cual la salida se bloquea con carácter previo a su presentación.")

    doc.add_heading("Sesgo", level=2)

    parrafo(doc,
            "El tratamiento del sesgo se articula en tres puntos del sistema. En las "
            "instrucciones de sistema, mediante una regla inquebrantable que prohíbe "
            "los estereotipos y obliga a señalar aquellos presentes en el texto de "
            "entrada. En las peticiones de generación de imágenes, mediante un "
            "detector de descriptores que fijan atributos personales sin necesidad "
            "funcional, dado que la mención de un rol profesional sin contexto "
            "adicional induce al modelo a reproducir el estereotipo predominante en su "
            "conjunto de entrenamiento. Y en la respuesta generada, mediante la "
            "revisión del texto con los mismos marcadores.")

    parrafo(doc,
            "El detector notifica sin bloquear, atendiendo al mismo criterio expuesto "
            "anteriormente: el objetivo consiste en que la persona adopte la decisión "
            "disponiendo de la información pertinente, y no en que la herramienta la "
            "adopte en su lugar. Un filtro de sesgo de carácter bloqueante tiende a "
            "ser desactivado por sus usuarios.")

    parrafo(doc,
            "Límite declarado: el mecanismo descrito detecta sesgo léxico en la "
            "petición, no sesgo en la imagen resultante. La evaluación de este último "
            "requeriría la generación de lotes y el análisis de la distribución "
            "demográfica de las salidas, lo que constituye una labor de auditoría "
            "periódica y no un control en línea.")

    doc.add_heading("Privacidad y derechos de autor", level=2)

    vineta_rica(doc, [
        ("Marcas registradas. ", True),
        ("La petición de generación de imágenes se contrasta con un listado de marcas "
         "protegidas. La producción de piezas que evoquen marcas ajenas expone a la "
         "agencia a una reclamación por infracción, motivo por el cual en este "
         "supuesto sí se procede al bloqueo.", False),
    ])
    vineta_rica(doc, [
        ("Estilos de autor. ", True),
        ("Se bloquean las peticiones que invocan el estilo de un artista vivo o de un "
         "estudio con obra protegida. El estilo debe describirse mediante sus "
         "atributos visuales y no mediante su autoría. Constituye el vector de riesgo "
         "más frecuente en la generación de imágenes para marketing.", False),
    ])
    vineta_rica(doc, [
        ("Procedencia. ", True),
        ("Cada imagen conserva su prompt, su estilo, su semilla, su autoría y la "
         "indicación expresa de haber sido generada mediante inteligencia artificial. "
         "Dichos metadatos permiten acreditar el procedimiento ante un eventual "
         "cuestionamiento por terceros, y responden a un requisito establecido por la "
         "propia guía de marca.", False),
    ])
    vineta_rica(doc, [
        ("Datos personales. ", True),
        ("La política prohíbe la transmisión de datos personales de clientes a los "
         "modelos. En un entorno productivo esta medida se reforzaría mediante la "
         "detección de información personal de Amazon Bedrock Guardrails, capaz de "
         "redactar automáticamente dichos datos con carácter previo a la inferencia.",
         False),
    ])
    vineta_rica(doc, [
        ("Cifrado. ", True),
        ("En un entorno productivo procedería aplicar cifrado en reposo con claves "
         "gestionadas por el cliente mediante KMS para el almacenamiento de imágenes y "
         "el historial, así como cifrado en tránsito, que Amazon Bedrock ya impone. En "
         "la presente entrega el almacenamiento es de sesión y no persiste, por lo que "
         "el cifrado en reposo no resulta aplicable; se documenta como requisito del "
         "paso a producción y no como elemento resuelto.", False),
    ])

    parrafo(doc,
            "En cuanto a la titularidad del contenido generado, se trata de una "
            "materia jurídicamente inestable que presenta variaciones según la "
            "jurisdicción. La política adoptada responde a un criterio de prudencia: "
            "no registrar las imágenes generadas como obra propia, no emplearlas como "
            "elemento central de una identidad de marca susceptible de registro, y "
            "documentar en todo caso el prompt y la semilla utilizados. No constituye "
            "una respuesta jurídica, sino una posición defendible en ausencia de la "
            "misma.")


def seccion_4(doc):
    doc.add_heading("4. Vía A · La aplicación desarrollada", level=1)

    parrafo(doc,
            "Aurora Studio es una aplicación web desarrollada con Streamlit y "
            "compuesta por cuatro pantallas. Cubre la totalidad del alcance mínimo "
            "exigido en la guía, así como el alcance ampliado en su integridad.")

    doc.add_heading("Alcance cubierto", level=2)

    tabla(doc,
          ["Requisito de la guía", "Estado", "Ubicación"],
          [
              ["Campo de texto que genera imagen con Stable Diffusion vía Bedrock",
               "Completo", "Pantalla «Generación de imágenes»"],
              ["Función que mejora texto con Claude (resumir y corregir como mínimo)",
               "Completo · cuatro operaciones", "Pantalla «Edición de contenido»"],
              ["Ambos flujos invocan Bedrock y presentan el resultado",
               "Completo · modo simulado", "Panel «Detalle técnico de la llamada»"],
              ["Selección de estilos y galería con descarga",
               "Completo · cuatro estilos", "Pantallas «Generación» y «Galería»"],
              ["Historial y control de versiones del texto",
               "Completo · con comparación visual", "Pantalla «Colaboración»"],
              ["Roles, permisos y comentarios",
               "Completo · tres roles, seis permisos", "Pantalla «Colaboración»"],
          ],
          anchos=[7.4, 4.2, 4.4])

    doc.add_heading("Procedimiento de ejecución", level=2)
    bloque_codigo(doc,
                  "pip install -r requirements.txt\n"
                  "python -m streamlit run app.py\n"
                  "\n"
                  "# Para invocar Amazon Bedrock de forma efectiva:\n"
                  "#   copiar .env.example a .env\n"
                  "#   BEDROCK_BACKEND=aws\n"
                  "#   AWS_REGION=us-east-1\n"
                  "#   aws configure",
                  tamano=9)
    parrafo(doc,
            "Se invoca Streamlit como módulo de Python y no mediante el comando "
            "directo por cuanto en numerosas instalaciones de Windows el directorio "
            "Scripts del intérprete no figura en la variable PATH, circunstancia que "
            "provoca el fallo del comando pese a estar el paquete correctamente "
            "instalado. La invocación como módulo emplea el mismo intérprete con el "
            "que se instalaron las dependencias.", tamano=10, color=GRIS)

    doc.add_heading("Evidencia de la corrección de la integración", level=2)

    parrafo(doc,
            "Dado que la aplicación no invoca efectivamente a Amazon Web Services, la "
            "evidencia de la corrección de la integración se aporta por tres vías "
            "complementarias.")

    vineta_rica(doc, [
        ("Petición visible en la interfaz. ", True),
        ("Cada operación presenta, en el panel «Detalle técnico de la llamada», el "
         "documento JSON exacto que se transmite a Amazon Bedrock, idéntico en modo "
         "simulado y en modo real.", False),
    ])
    vineta_rica(doc, [
        ("Validación de contrato en el sustituto. ", True),
        ("La clase MockBedrockRuntime rechaza las peticiones mal formadas aplicando "
         "los mismos criterios que el proveedor.", False),
    ])
    vineta_rica(doc, [
        ("Pruebas automatizadas. ", True),
        ("El módulo tests/test_contratos_bedrock.py verifica la estructura de las "
         "peticiones dirigidas a los tres modelos y el comportamiento de los controles "
         "de seguridad; el módulo tests/test_rag_umbral.py reproduce la calibración "
         "del umbral de recuperación.", False),
    ])


def seccion_5(doc):
    doc.add_heading("5. Limitaciones declaradas", level=1)

    parrafo(doc,
            "La enumeración de las limitaciones forma parte del trabajo: un diseño que "
            "no reconoce sus propios límites no puede considerarse concluido.")

    tabla(doc,
          ["Limitación", "Alcance efectivo", "Requisito de superación"],
          [
              ["Ausencia de ejecución contra Amazon Web Services",
               "Ninguna respuesta procede de los modelos reales.",
               "Cuenta con acceso concedido a los tres modelos y configuración "
               "BEDROCK_BACKEND=aws."],
              ["Calidad del sustituto de representaciones vectoriales",
               "Opera como recuperador léxico y no semántico. Recall@3 medido: 5 de 8 "
               "consultas. Presenta fallos en aquellas que exigen comprensión del "
               "significado y no coincidencia de términos.",
               "Amazon Titan en modo real. Cabe esperar una mejora sin modificación "
               "del código de aplicación."],
              ["Moderación mediante listas",
               "Detecta las infracciones evidentes; no constituye un clasificador.",
               "Amazon Bedrock Guardrails como segunda capa."],
              ["Autorización sin autenticación",
               "El selector de usuario simula una sesión iniciada. No existen "
               "contraseñas ni verificación de identidad.",
               "Amazon Cognito o el sistema de identidad corporativo. El módulo de "
               "permisos se encuentra ya desacoplado y no requeriría reescritura."],
              ["Ausencia de persistencia",
               "La galería y el historial residen en memoria y se pierden al "
               "reiniciar.",
               "DynamoDB para el historial y S3 para las imágenes, con cifrado "
               "mediante KMS."],
              ["Concurrencia efectiva",
               "La colaboración es multiusuario en el modelo de roles, si bien opera "
               "sobre un único proceso de Streamlit.",
               "Servidor con estado compartido y bloqueo optimista por versión."],
          ],
          anchos=[4.0, 6.6, 5.4])


def seccion_6(doc):
    doc.add_heading("6. Autoevaluación frente a la guía", level=1)

    parrafo(doc,
            "Se contrasta a continuación la entrega con los puntos de verificación "
            "establecidos en la guía del trabajo práctico.")

    filas = [
        ["Definición del problema e historias de usuario", "Sí", "3.1"],
        ["Diagrama con interfaz, wrapper, Bedrock y almacenamiento", "Sí", "3.2"],
        ["Justificación de API gestionada frente a despliegue propio", "Sí", "3.2"],
        ["Modelo y parámetros por tarea, debidamente justificados", "Sí", "3.3"],
        ["Instrucciones de sistema con los cuatro pilares", "Sí", "3.4"],
        ["Uso justificado y diferenciado de RAG y memoria", "Sí", "3.5"],
        ["Moderación, inyección de prompt, sesgo, privacidad y copyright", "Sí", "3.6"],
        ["Generación de imagen y mejora de texto mediante Bedrock",
         "Sí · modo simulado", "4"],
        ["Código acompañado de README con instrucciones de ejecución", "Sí",
         "README.md"],
        ["Demostración mediante capturas comentadas", "Plantilla preparada",
         "docs/Plantilla_Capturas_Demo.docx"],
        ["Citación de fuentes y herramientas", "Sí", "7"],
    ]
    tabla(doc, ["Punto de verificación", "Estado", "Apartado"], filas,
          anchos=[10.6, 3.4, 2.0])


def seccion_7(doc):
    doc.add_heading("7. Fuentes y herramientas", level=1)

    parrafo(doc, "Documentación oficial consultada:", negrita=True)
    for fuente in [
        "Amazon Bedrock — Guía del usuario y referencia de la API de inferencia: "
        "estructura de la operación invoke_model y formatos de petición y respuesta "
        "por proveedor.",
        "Anthropic Claude en Amazon Bedrock — Parámetros de inferencia y formato de la "
        "Messages API: anthropic_version, system, messages, temperature y top_p.",
        "Stability AI Stable Diffusion XL en Amazon Bedrock — Contrato de los campos "
        "text_prompts, cfg_scale, steps, seed y style_preset.",
        "Amazon Titan Embeddings — Parámetros inputText, dimensions y normalize.",
        "Amazon Bedrock Guardrails — Políticas de contenido y detección de información "
        "personal. Se cita como trabajo futuro; no se ha implementado en esta entrega.",
        "Documentación de Streamlit — Gestión del estado de sesión y ciclo de "
        "reejecución del script.",
    ]:
        vineta(doc, fuente)

    parrafo(doc, "Herramientas empleadas:", negrita=True)
    for herramienta in [
        "Python 3.14 · Streamlit 1.63 · boto3 · NumPy · Pillow · Matplotlib · "
        "python-docx",
        "Claude Code (Anthropic), empleado como asistente de desarrollo durante la "
        "implementación.",
    ]:
        vineta(doc, herramienta)

    parrafo(doc,
            "Los materiales de la asignatura —enunciado del caso práctico y guía del "
            "trabajo práctico de la Unidad 3— constituyen la base de los requisitos "
            "recogidos en el presente documento.", tamano=10, color=GRIS)


# ---------------------------------------------------------------------------


def construir() -> Path:
    doc = Document()

    seccion = doc.sections[0]
    seccion.top_margin = Cm(2.2)
    seccion.bottom_margin = Cm(2.2)
    seccion.left_margin = Cm(2.4)
    seccion.right_margin = Cm(2.4)

    configurar_estilos(doc)
    pie_de_pagina(doc)

    portada(doc)
    seccion_indice(doc)
    seccion_1(doc)
    doc.add_page_break()

    doc.add_heading("Tronco común", level=1)
    parrafo(doc,
            "Las seis secciones exigidas por igual en ambas vías de entrega. Se "
            "conserva deliberadamente su numeración original (3.1 a 3.6) con el fin de "
            "facilitar el contraste punto por punto con la guía del trabajo práctico.",
            cursiva=True, color=GRIS)

    seccion_31(doc)
    seccion_32(doc)
    doc.add_page_break()
    seccion_33(doc)
    doc.add_page_break()
    seccion_34(doc)
    doc.add_page_break()
    seccion_35(doc)
    doc.add_page_break()
    seccion_36(doc)
    doc.add_page_break()
    seccion_4(doc)
    seccion_5(doc)
    doc.add_page_break()
    seccion_6(doc)
    seccion_7(doc)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    destino = DOCS_DIR / "Memoria_CasoPractico_U3_Jose_Ruber_Moncayo_Navia.docx"
    doc.save(destino)
    return destino


if __name__ == "__main__":
    ruta = construir()
    print(f"Memoria generada: {ruta}")
