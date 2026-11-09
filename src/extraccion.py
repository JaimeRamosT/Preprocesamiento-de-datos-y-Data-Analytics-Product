"""Etapa 1 · Ingestión: extracción de ofertas laborales públicas de Talento Perú (SERVIR).

Versión 2.0 del extractor de la Parte 1. Cambios respecto a la Parte 1:

1. Cada corte se guarda en su propio archivo con fecha
   (``data/raw/talento_peru_ofertas_AAAAMMDD.csv``). El dataset inicial
   ``data/raw/talento_peru_ofertas.csv`` queda congelado y no se puede sobrescribir.
2. ``fecha_extraccion_utc`` se registra por página, igual que en la corrida
   que generó el dataset inicial (el notebook de la Parte 1 la calculaba una sola vez).
3. ``crear_navegador`` funciona en Linux/Colab (Chromium + ChromeDriver en el PATH)
   y en Windows/macOS (Google Chrome + Selenium Manager, que descarga el driver solo).
4. Al terminar, o si la corrida se interrumpe, se guarda un archivo de estado JSON.
5. Si el id autogenerado del botón "Siguiente" cambia, se busca el botón por su texto.
6. Las rutas salen de ``src/config.py``.

El parseo, la limpieza en línea y el hash SHA-256 son los mismos de la Parte 1,
por eso ``id_oferta_hash`` se puede recalcular sobre el dataset inicial.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from src import config

VERSION_EXTRACTOR = "2.0"

SELECTOR_OFERTAS = ".cuadro-vacantes"
ID_SIGUIENTE = "frmLstOfertsLabo:j_idt56"  # id autogenerado por JSF: puede cambiar
XPATH_SIGUIENTE = "//*[self::a or self::button][contains(normalize-space(.), 'Sig')]"
PATRON_PAGINA = re.compile(r"Página\s+(\d+)\s+de\s+(\d+)", re.IGNORECASE)
PATRON_NUMERO = re.compile(r"-?\d+(?:,\d{3})*(?:\.\d+)?")
ESPERA_SEGUNDOS = 20


# --- Limpieza en línea (igual que en la Parte 1) ------------------------------------

def limpiar_texto(valor: str | None) -> str:
    """Quita espacios duplicados y espacios no separables (\\xa0)."""
    return " ".join((valor or "").replace("\xa0", " ").split())


def obtener_valor(tarjeta, etiqueta: str) -> str:
    """Devuelve el texto del ``span.detalle-sp`` que sigue a la etiqueta indicada."""
    for titulo in tarjeta.select("span.sub-titulo"):
        if etiqueta in limpiar_texto(titulo.get_text(" ", strip=True)):
            detalle = titulo.find_next("span", class_="detalle-sp")
            if detalle:
                return limpiar_texto(detalle.get_text(" ", strip=True))
    return ""


def convertir_entero(valor: str) -> int | None:
    coincidencia = re.search(r"\d+", valor)
    return int(coincidencia.group(0)) if coincidencia else None


def convertir_numero(valor: str) -> float | None:
    coincidencia = PATRON_NUMERO.search(valor)
    return float(coincidencia.group(0).replace(",", "")) if coincidencia else None


def convertir_fecha(valor: str) -> str | None:
    """DD/MM/AAAA -> AAAA-MM-DD (ISO 8601)."""
    try:
        return datetime.strptime(limpiar_texto(valor), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def calcular_hash(oferta: dict) -> str:
    """SHA-256 de los 8 campos principales unidos por '|', recortado a 24 caracteres."""
    texto_clave = "|".join(str(oferta[campo]) for campo in config.CAMPOS_PRINCIPALES)
    return hashlib.sha256(texto_clave.encode("utf-8")).hexdigest()[:24]


def extraer_oferta(tarjeta, pagina: int, fecha_extraccion: str) -> dict | None:
    """Convierte una tarjeta HTML en un registro. Devuelve None si falta un campo principal."""
    titulo = tarjeta.select_one(".titulo-vacante label")
    entidad = tarjeta.select_one(".nombre-entidad .detalle-sp")

    oferta = {
        "puesto": limpiar_texto(titulo.get_text(" ", strip=True) if titulo else ""),
        "entidad": limpiar_texto(entidad.get_text(" ", strip=True) if entidad else ""),
        "ubicacion": obtener_valor(tarjeta, "Ubicación:"),
        "numero_convocatoria": obtener_valor(tarjeta, "Número de Convocatoria:"),
        "vacantes": convertir_entero(obtener_valor(tarjeta, "Cantidad de Vacantes:")),
        "remuneracion_pen": convertir_numero(obtener_valor(tarjeta, "Remuneración:")),
        "fecha_inicio_publicacion": convertir_fecha(obtener_valor(tarjeta, "Fecha Inicio de Publicación:")),
        "fecha_fin_publicacion": convertir_fecha(obtener_valor(tarjeta, "Fecha Fin de Publicación:")),
        "pagina_origen": pagina,
        "fuente_url": config.URL_FUENTE,
        "fecha_extraccion_utc": fecha_extraccion,
    }

    if any(oferta[campo] in (None, "") for campo in config.CAMPOS_PRINCIPALES):
        return None

    oferta[config.COLUMNA_ID] = calcular_hash(oferta)
    return {campo: oferta[campo] for campo in config.CAMPOS}


def obtener_pagina(html: str) -> tuple[int, int]:
    """Lee el indicador 'Página X de Y' del listado."""
    texto = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    coincidencia = PATRON_PAGINA.search(texto)
    if not coincidencia:
        raise RuntimeError("No se encontró el indicador de paginación.")
    return int(coincidencia.group(1)), int(coincidencia.group(2))


def extraer_pagina(html: str, pagina: int, fecha_extraccion: str) -> tuple[list[dict], int]:
    """Extrae todas las tarjetas de una página. Devuelve (ofertas válidas, tarjetas incompletas)."""
    soup = BeautifulSoup(html, "html.parser")
    ofertas, incompletas = [], 0
    for tarjeta in soup.select(SELECTOR_OFERTAS):
        oferta = extraer_oferta(tarjeta, pagina, fecha_extraccion)
        if oferta is None:
            incompletas += 1
        else:
            ofertas.append(oferta)
    return ofertas, incompletas


# --- Archivos ---------------------------------------------------------------------------

def ruta_corte(fecha: datetime | None = None) -> Path:
    """Archivo de un corte nuevo: data/raw/talento_peru_ofertas_AAAAMMDD.csv."""
    fecha = fecha or datetime.now()
    return config.DIR_RAW / f"talento_peru_ofertas_{fecha:%Y%m%d}.csv"


def ruta_estado(archivo: Path) -> Path:
    """Archivo de estado asociado a un corte (mismo nombre, 'ofertas' -> 'estado', .json)."""
    archivo = Path(archivo)
    return archivo.with_name(archivo.stem.replace("ofertas", "estado") + ".json")


def leer_claves(archivo: Path) -> set[str]:
    if not Path(archivo).exists():
        return set()
    with Path(archivo).open("r", encoding=config.ENCODING, newline="") as f:
        return {fila[config.COLUMNA_ID] for fila in csv.DictReader(f)}


def guardar_ofertas(filas: list[dict], archivo: Path) -> None:
    """Agrega filas al CSV del corte (almacenamiento incremental, UTF-8)."""
    archivo = Path(archivo)
    existe = archivo.exists()
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with archivo.open("a", encoding=config.ENCODING, newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=config.CAMPOS)
        if not existe:
            escritor.writeheader()
        escritor.writerows(filas)


def guardar_estado(estado: dict, archivo_estado: Path) -> None:
    Path(archivo_estado).write_text(
        json.dumps(estado, ensure_ascii=False, indent=2), encoding=config.ENCODING
    )


def resumen_corte(archivo: Path) -> dict:
    """Resume un CSV ya extraído (sirve para reconstruir el estado de una corrida)."""
    with Path(archivo).open("r", encoding=config.ENCODING, newline="") as f:
        filas = list(csv.DictReader(f))
    paginas = sorted({int(f["pagina_origen"]) for f in filas})
    marcas = sorted(f["fecha_extraccion_utc"] for f in filas)
    inicio = datetime.fromisoformat(marcas[0]) if marcas else None
    fin = datetime.fromisoformat(marcas[-1]) if marcas else None
    return {
        "archivo": Path(archivo).name,
        "ofertas": len(filas),
        "ofertas_unicas": len({f[config.COLUMNA_ID] for f in filas}),
        "paginas_con_ofertas": len(paginas),
        "pagina_inicial": paginas[0] if paginas else None,
        "pagina_final": paginas[-1] if paginas else None,
        "primera_pagina_utc": marcas[0] if marcas else None,
        "ultima_pagina_utc": marcas[-1] if marcas else None,
        "segundos_entre_primera_y_ultima_pagina": round((fin - inicio).total_seconds(), 1) if marcas else None,
    }


# --- Navegador ------------------------------------------------------------------------

def crear_navegador(headless: bool = True):
    """Chrome sin interfaz. Usa Chromium + ChromeDriver del PATH si existen (Linux/Colab);
    si no, Google Chrome con Selenium Manager (Windows/macOS, Selenium ≥ 4.6)."""
    from selenium import webdriver
    from selenium.common.exceptions import WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    opciones = Options()
    if headless:
        opciones.add_argument("--headless=new")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--window-size=1440,1200")

    ruta_chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    ruta_driver = shutil.which("chromedriver")
    if ruta_chromium and ruta_driver:
        opciones.binary_location = ruta_chromium
        return webdriver.Chrome(service=Service(ruta_driver), options=opciones)

    try:
        return webdriver.Chrome(options=opciones)
    except WebDriverException as error:
        raise RuntimeError(
            "No se pudo iniciar Chrome. Instale Google Chrome (Windows/macOS) o "
            "Chromium + ChromeDriver (Linux/Colab) y vuelva a intentar."
        ) from error


def _boton_siguiente(navegador):
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    try:
        return navegador.find_element(By.ID, ID_SIGUIENTE)
    except NoSuchElementException:
        candidatos = navegador.find_elements(By.XPATH, XPATH_SIGUIENTE)
        return candidatos[0] if candidatos else None


def _boton_activo(boton) -> bool:
    clases = boton.get_attribute("class") or ""
    return boton.is_enabled() and "ui-state-disabled" not in clases


# --- Extracción --------------------------------------------------------------------

def extraer_listado(limite: int, pausa: float = 2, archivo: Path | None = None,
                    headless: bool = True) -> dict:
    """Recorre el listado página a página hasta reunir ``limite`` ofertas únicas.

    Es idempotente: si el archivo del corte ya existe, carga sus hashes y continúa
    sin duplicar. Devuelve el estado de la corrida, que también se guarda en JSON.
    """
    archivo = Path(archivo) if archivo else ruta_corte()
    if archivo.resolve() == config.ARCHIVO_RAW.resolve():
        raise ValueError(
            "El dataset inicial está congelado. Use un archivo nuevo para cada corte "
            "(por defecto, data/raw/talento_peru_ofertas_AAAAMMDD.csv)."
        )

    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait

    claves = leer_claves(archivo)
    estado = {
        "version_extractor": VERSION_EXTRACTOR,
        "fuente_url": config.URL_FUENTE,
        "archivo": archivo.name,
        "limite": limite,
        "pausa_segundos": pausa,
        "ofertas_previas_en_archivo": len(claves),
        "inicio_utc": datetime.now(timezone.utc).isoformat(),
        "paginas_recorridas": 0,
        "pagina_inicial": None,
        "pagina_final": None,
        "paginas_totales_portal": None,
        "ofertas_nuevas": 0,
        "tarjetas_incompletas": 0,
        "ofertas_repetidas": 0,
        "motivo_fin": None,
    }

    navegador = crear_navegador(headless)
    try:
        navegador.get(config.URL_FUENTE)
        WebDriverWait(navegador, ESPERA_SEGUNDOS).until(
            lambda p: len(p.find_elements(By.CSS_SELECTOR, SELECTOR_OFERTAS)) > 0
        )

        while len(claves) < limite:
            html = navegador.page_source
            pagina_actual, paginas_totales = obtener_pagina(html)
            fecha_extraccion = datetime.now(timezone.utc).isoformat()  # una marca por página

            ofertas, incompletas = extraer_pagina(html, pagina_actual, fecha_extraccion)
            nuevas = []
            for oferta in ofertas:
                if oferta[config.COLUMNA_ID] in claves:
                    estado["ofertas_repetidas"] += 1
                    continue
                nuevas.append(oferta)
                claves.add(oferta[config.COLUMNA_ID])
                if len(claves) >= limite:
                    break
            guardar_ofertas(nuevas, archivo)

            estado["paginas_recorridas"] += 1
            estado["pagina_inicial"] = estado["pagina_inicial"] or pagina_actual
            estado["pagina_final"] = pagina_actual
            estado["paginas_totales_portal"] = paginas_totales
            estado["ofertas_nuevas"] += len(nuevas)
            estado["tarjetas_incompletas"] += incompletas
            print(f"Página {pagina_actual} de {paginas_totales} | ofertas en el corte: {len(claves)}")

            if len(claves) >= limite:
                estado["motivo_fin"] = "límite alcanzado"
                break
            if pagina_actual >= paginas_totales:
                estado["motivo_fin"] = "última página del portal"
                break

            time.sleep(pausa)  # no sobrecargar el servidor público
            boton = _boton_siguiente(navegador)
            if boton is None or not _boton_activo(boton):
                estado["motivo_fin"] = "botón 'Siguiente' no disponible"
                break
            boton.click()
            WebDriverWait(navegador, ESPERA_SEGUNDOS).until(
                lambda p: obtener_pagina(p.page_source)[0] != pagina_actual
            )
    except Exception as error:
        estado["motivo_fin"] = f"error: {type(error).__name__}: {error}"
        raise
    finally:
        navegador.quit()
        fin = datetime.now(timezone.utc)
        estado["fin_utc"] = fin.isoformat()
        estado["duracion_segundos"] = round(
            (fin - datetime.fromisoformat(estado["inicio_utc"])).total_seconds(), 1
        )
        estado["ofertas_en_archivo"] = len(claves)
        guardar_estado(estado, ruta_estado(archivo))

    return estado
