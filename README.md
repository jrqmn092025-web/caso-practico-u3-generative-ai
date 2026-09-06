# Aurora Studio

Herramienta interna de generación de imágenes y edición de contenido para una
agencia de marketing, construida sobre **Amazon Bedrock**.

**Caso Práctico · Unidad 3 · Generative AI · Instituto Europeo de Posgrado**
Autor: José Ruber Moncayo Navia · Vía A (aplicación funcional)

---

## Aviso sobre el modo de ejecución

Esta aplicación se entrega funcionando en **modo simulado**: no llama a Amazon
Bedrock porque no se dispone de cuenta AWS. La guía del trabajo contempla
expresamente esta opción.

Lo que sí es real: **todo el código de integración**. La simulación se aplica en
la frontera de transporte, sustituyendo el cliente `bedrock-runtime` de boto3
por un doble que expone la misma operación `invoke_model`, recibe el mismo
cuerpo JSON y devuelve la misma estructura de respuesta. La aplicación construye
los payloads reales, los serializa igual y parsea las respuestas por el mismo
camino.

Conmutar a AWS real no requiere tocar una sola línea de código:

```bash
BEDROCK_BACKEND=aws
```

---

## Instalación y ejecución

Requiere **Python 3.10 o superior** (desarrollado y probado en 3.14).

```bash
pip install -r requirements.txt
```

```bash
python -m streamlit run app.py
```

La aplicación abre en `http://localhost:8501`. No necesita credenciales ni
configuración: arranca en modo simulado por defecto.

> **Por qué `python -m streamlit` y no `streamlit` a secas.** En muchas
> instalaciones de Windows, la carpeta `Scripts` de Python no está en el `PATH`,
> y `streamlit run app.py` falla con *«no se reconoce como nombre de un
> cmdlet»* aunque el paquete esté correctamente instalado. Invocarlo como módulo
> usa el mismo intérprete con el que hiciste `pip install` y funciona siempre.

### Ejecutar contra AWS real

1. Copia `.env.example` a `.env` y pon `BEDROCK_BACKEND=aws`.
2. Solicita acceso a los modelos en la consola de Bedrock → *Model access*:
   Anthropic Claude, Stability AI Stable Diffusion y Amazon Titan Embeddings.
   El acceso es **por región**; `us-east-1` y `us-west-2` tienen la cobertura
   más amplia.
3. Configura credenciales:

```bash
aws configure
```

Los errores más frecuentes (modelo no habilitado, región equivocada, sin
credenciales) se traducen a mensajes accionables en `src/bedrock/client.py`.

---

## Despliegue

> **Vercel no puede ejecutar esta aplicación.** No se trata de un fallo de
> configuración: es una incompatibilidad de fondo. Vercel ejecuta funciones
> *serverless* (una petición, una respuesta, proceso efímero) y sitios
> estáticos. Streamlit necesita justo lo contrario: un proceso persistente que
> mantenga abierto un WebSocket con cada navegador conectado, porque ahí es
> donde vive el estado de sesión. No existe *runtime* de Streamlit para Vercel,
> y ningún `vercel.json` lo arregla. Si hay un proyecto de Vercel apuntando a
> este repositorio, conviene eliminarlo para que no siga acumulando
> despliegues fallidos en cada `push`.

**La plataforma adecuada es Streamlit Community Cloud**, que es gratuita y está
hecha exactamente para esto:

1. Entrar en `https://share.streamlit.io` e iniciar sesión con la cuenta de
   GitHub.
2. *New app* → seleccionar el repositorio, la rama `main` y el fichero
   principal `app.py`.
3. En *Advanced settings*, elegir una versión de Python **3.11 o superior**.
4. Desplegar.

No hace falta configuración adicional: el `requirements.txt` de la raíz ya
declara las dependencias y la aplicación arranca en modo simulado por defecto,
sin requerir credenciales de AWS.

Alternativas válidas si se prefiere otro proveedor: Hugging Face Spaces (con
SDK *Streamlit*), Render, Railway o Fly.io. Todas ejecutan procesos
persistentes, que es el requisito real.

> **El despliegue no forma parte de lo exigido.** La guía del trabajo pide el
> código en un repositorio, un README con instrucciones de ejecución y una
> demostración. Publicar la aplicación es alcance adicional.

---

## Qué hace

| Pantalla | Funcionalidad |
|---|---|
| **Generación de imágenes** | Texto → imagen con Stable Diffusion XL. Cuatro estilos, control de semilla, procedencia completa. |
| **Edición de contenido** | Cuatro operaciones con Claude: resumir, expandir, corregir y generar variaciones. Cada una con su modelo y sus parámetros. |
| **Colaboración** | Historial de versiones solo-anexado, comparación visual de cambios, comentarios, ciclo de aprobación y matriz de permisos. |
| **Galería** | Catálogo de la sesión con filtros por estilo y autor, descarga y procedencia. |

Transversal a todas: moderación de entrada y salida, defensa frente a inyección
de prompt, revisión de sesgo, bloqueo por copyright y RAG sobre la guía de
estilo de marca.

---

## Modelos y parámetros

| Tarea | Modelo | Temp. | Top-P | Máx. tokens |
|---|---|---|---|---|
| Corregir | `anthropic.claude-haiku-4-5` | 0.0 | 0.9 | 2048 |
| Resumir | `anthropic.claude-haiku-4-5` | 0.2 | 0.9 | 1024 |
| Expandir | `anthropic.claude-sonnet-4-6` | 0.7 | 0.95 | 4096 |
| Variar | `anthropic.claude-sonnet-4-6` | 0.9 | 0.95 | 3072 |
| Imágenes | `stability.stable-diffusion-xl-v1` | — | — | — |
| Embeddings | `amazon.titan-embed-text-v2:0` | — | — | — |

La justificación de cada valor vive en `src/bedrock/models.py`, se muestra en la
propia interfaz y alimenta la tabla de la memoria. Un solo origen para los tres.

---

## Estructura del proyecto

```
app.py                        Punto de entrada de Streamlit
src/
  config.py                   Configuración y variables de entorno
  bedrock/
    models.py                 Catálogo de modelos y perfiles de inferencia
    client.py                 Wrapper: payloads, invocación y parseo
    mock_runtime.py           Doble de transporte + validación de contratos
  prompts/system_prompts.py   System prompts (los cuatro pilares)
  security/
    moderation.py             Moderación de entrada y salida, sesgo, copyright
    prompt_guard.py           Defensa frente a inyección de prompt
  services/
    text_service.py           Orquestación de la edición de contenido
    image_service.py          Generación de imágenes y procedencia
    rag_service.py            Índice vectorial de la guía de marca
  domain/
    auth.py                   Roles y permisos
    versioning.py             Piezas, versiones y comentarios
  ui/                         Las cuatro pantallas
data/brand_guide/             Corpus de la guía de estilo (fuente del RAG)
docs/                         Memoria en Word y guion de la demostración
scripts/                      Generadores del diagrama y de la memoria
tests/                        Contratos de Bedrock y calibración del RAG
```

---

## Pruebas

```bash
python tests/test_contratos_bedrock.py
```

18 pruebas que verifican la forma de las peticiones a los tres modelos, el
rechazo de payloads inválidos, los controles de seguridad, la separación de
funciones entre roles y la integridad del historial.

```bash
python tests/test_rag_umbral.py
```

Reproduce la calibración del umbral de similitud del RAG sobre dos poblaciones
de consultas (legítimas y de ruido) y reporta el recall.

---

## Regenerar los entregables

```bash
python scripts/generar_diagrama.py
```

```bash
python scripts/generar_memoria.py
```

```bash
python scripts/generar_plantilla_capturas.py
```

El diagrama de arquitectura y la memoria en Word se generan desde el código, no
se mantienen a mano. La tabla de parámetros y el texto del system prompt que
aparecen en la memoria se leen de `src/bedrock/models.py` y
`src/prompts/system_prompts.py`, de modo que el documento no puede afirmar algo
que la aplicación no haga.

---

## Limitaciones declaradas

- **No se ejecuta contra AWS.** Ninguna respuesta procede de los modelos reales.
- **El sustituto de embeddings es léxico, no semántico.** Recall@3 medido: 5 de
  8 consultas. Con Titan real se espera que suba sin tocar código de aplicación.
- **La moderación es por listas y reglas**, no un clasificador. En producción
  sería la primera de tres capas, con Bedrock Guardrails como segunda.
- **Hay autorización, pero no autenticación.** El selector de usuario simula una
  sesión iniciada; no es un control de seguridad.
- **El estado no persiste.** Galería e historial viven en memoria y se pierden
  al reiniciar.

La memoria (`docs/`) desarrolla cada una con lo que haría falta para superarla.

---

## Documentación

- `docs/Memoria_CasoPractico_U3_Jose_Ruber_Moncayo_Navia.docx` — memoria
  completa: tronco común (3.1–3.6), ejecución de la Vía A, limitaciones y
  autoevaluación.
- `docs/Plantilla_Capturas_Demo.docx` — anexo de la demostración con los ocho
  marcos ya reservados para insertar las capturas y los pies de figura
  redactados. Es el documento que se entrega.
- `docs/GUION_DEMO.md` — guion de trabajo de las ocho capturas: qué reproducir
  en pantalla y qué debe resultar visible en cada una.
- `assets/arquitectura.png` — diagrama de arquitectura.
