"""Rutas y constantes compartidas por todas las etapas del pipeline.

Cada notebook y script importa este módulo en lugar de escribir rutas a mano.
Así el proyecto funciona igual en Windows, Linux, macOS o Colab, y desde
cualquier carpeta en la que se abra el notebook.
"""

from pathlib import Path

# --- Raíz del repositorio -------------------------------------------------
# src/config.py -> src/ -> raíz
RAIZ = Path(__file__).resolve().parents[1]

# --- Carpetas ---------------------------------------------------------------
DIR_DATA = RAIZ / "data"
DIR_RAW = DIR_DATA / "raw"              # datos tal como se extrajeron (solo lectura)
DIR_INTERIM = DIR_DATA / "interim"      # salidas intermedias de limpieza y transformación
DIR_PROCESSED = DIR_DATA / "processed"  # dataset final entregable
DIR_NOTEBOOKS = RAIZ / "notebooks"
DIR_DOCS = RAIZ / "docs"
DIR_REPORTS = RAIZ / "reports"
DIR_FIGURAS = DIR_REPORTS / "figures"

# --- Archivos de cada etapa (contratos de datos) ---------------------------
# Etapa 1 · Ingestión (Integrante 1). Corte del 17-18 de septiembre de 2026.
ARCHIVO_RAW = DIR_RAW / "talento_peru_ofertas.csv"
ARCHIVO_ESTADO_RAW = DIR_RAW / "talento_peru_estado.json"
# Etapa 2 · Limpieza (Integrante 2)
ARCHIVO_LIMPIO = DIR_INTERIM / "talento_peru_limpio.csv"
# Etapa 3 · Transformación (Integrante 3)
ARCHIVO_TRANSFORMADO = DIR_INTERIM / "talento_peru_transformado.csv"
# Etapa 4 · Feature Engineering (Integrante 4) -> dataset final
ARCHIVO_FINAL = DIR_PROCESSED / "talento_peru_final.csv"

# Diccionarios de datos en formato legible por máquina (los PDF se generan a partir de ellos)
DICCIONARIO_INICIAL = DIR_DOCS / "diccionario_datos_inicial.csv"
DICCIONARIO_FINAL = DIR_DOCS / "diccionario_datos_final.csv"

# Formato de todos los CSV del proyecto
ENCODING = "utf-8"

# --- Fuente -----------------------------------------------------------------
URL_FUENTE = (
    "https://app.servir.gob.pe/DifusionOfertasExterno/faces/consultas/"
    "ofertas_laborales.xhtml"
)

# --- Esquema del dataset inicial -------------------------------------------
CAMPOS = [
    "id_oferta_hash", "puesto", "entidad", "ubicacion",
    "numero_convocatoria", "vacantes", "remuneracion_pen",
    "fecha_inicio_publicacion", "fecha_fin_publicacion",
    "pagina_origen", "fuente_url", "fecha_extraccion_utc",
]

# Campos que describen la oferta: no pueden estar vacíos y forman el hash
CAMPOS_PRINCIPALES = [
    "puesto", "entidad", "ubicacion", "numero_convocatoria",
    "vacantes", "remuneracion_pen", "fecha_inicio_publicacion",
    "fecha_fin_publicacion",
]

COLUMNA_ID = "id_oferta_hash"
COLUMNAS_FECHA = ["fecha_inicio_publicacion", "fecha_fin_publicacion"]

# --- Parámetros que definen otras etapas -----------------------------------
# Umbral mínimo de remuneración plausible (S/ por mes). Lo define y justifica
# el Integrante 2 en 02_limpieza_datos.ipynb. Mientras sea None, la validación
# solo informa los valores sospechosos y no detiene el pipeline.
UMBRAL_REMUNERACION_MINIMA = None

# Semilla para procesos aleatorios, p. ej. KMeans(random_state=config.SEMILLA) (reproducibilidad)
SEMILLA = 42


def asegurar_carpetas():
    """Crea las carpetas de salida si no existen (no toca data/raw)."""
    for carpeta in (DIR_INTERIM, DIR_PROCESSED, DIR_FIGURAS):
        carpeta.mkdir(parents=True, exist_ok=True)
