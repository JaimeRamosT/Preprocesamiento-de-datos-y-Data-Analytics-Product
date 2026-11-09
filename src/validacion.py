"""Validación de los contratos de datos entre etapas del pipeline.

Cada etapa entrega un archivo y, antes de que la siguiente lo use, se revisa:

* **Errores**: rompen el contrato (columnas faltantes, ids duplicados, nulos
  en campos obligatorios, tipos incorrectos). Detienen el pipeline.
* **Advertencias**: valores sospechosos que alguien debe revisar y justificar
  (por ejemplo, remuneraciones no plausibles en el dataset crudo). No detienen
  el pipeline.

Uso desde un notebook::

    from src import validacion
    validacion.validar("limpio").exigir()

Uso desde la terminal (en la raíz del repositorio)::

    python -m src.validacion            # valida todas las etapas que ya tienen archivo
    python -m src.validacion raw limpio # valida solo esas etapas
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src import config

LIMITE_NULOS_FINAL = 0.10  # objetivo de calidad de la Parte 1: ≤ 10 % de nulos por columna


class ValidacionError(Exception):
    """Se lanza cuando un archivo no cumple el contrato de su etapa."""


@dataclass
class Resultado:
    etapa: str
    archivo: Path
    filas: int = 0
    columnas: int = 0
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores

    def exigir(self) -> "Resultado":
        """Muestra el reporte y lanza ValidacionError si hay errores."""
        print(self)
        if self.errores:
            raise ValidacionError(
                f"La etapa '{self.etapa}' no cumple su contrato: "
                f"{len(self.errores)} error(es). Revise el reporte anterior."
            )
        return self

    def __str__(self) -> str:
        try:
            ruta = self.archivo.relative_to(config.RAIZ)
        except ValueError:
            ruta = self.archivo
        estado = "OK" if self.ok else "FALLA"
        lineas = [f"[{estado}] {self.etapa}: {ruta} ({self.filas} filas, {self.columnas} columnas)"]
        lineas += [f"  ERROR: {e}" for e in self.errores]
        lineas += [f"  ADVERTENCIA: {a}" for a in self.advertencias]
        return "\n".join(lineas)


# --- Lectura -------------------------------------------------------------------

def cargar(ruta: Path) -> pd.DataFrame:
    """Lee un CSV del proyecto con la codificación acordada."""
    return pd.read_csv(ruta, encoding=config.ENCODING)


# Nombres de tipos que acepta cada contrato (se comparan con df[col].dtype, como en df.info())
TIPOS_ENTEROS = ["int64", "int32", "Int64"]
TIPOS_NUMERICOS = TIPOS_ENTEROS + ["float64", "float32", "Float64"]


def _vacios(serie: pd.Series) -> pd.Series:
    """Máscara booleana: True si el valor es nulo o una cadena vacía."""
    return serie.isnull() | (serie == "")


def _fecha_invalida(valor) -> bool:
    """True si el valor no es nulo y no está en formato AAAA-MM-DD (se usa con apply)."""
    if pd.isnull(valor):
        return False
    try:
        pd.to_datetime(valor, format="%Y-%m-%d")
        return False
    except (ValueError, TypeError):
        return True


def _es_solo_numero(valor) -> bool:
    """True si el texto es solo un número, como el puesto '1' (se usa con apply)."""
    return str(valor).strip().isdigit()


def _calcular_hash(fila) -> str:
    """SHA-256 de los 8 campos principales unidos por '|' (mismo cálculo de la extracción)."""
    clave = "|".join(fila[c] for c in config.CAMPOS_PRINCIPALES)
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:24]


# --- Chequeos reutilizables ------------------------------------------------------

def _columnas_exactas(df, esperadas, r: Resultado):
    if list(df.columns) != list(esperadas):
        faltan = [c for c in esperadas if c not in df.columns]
        sobran = [c for c in df.columns if c not in esperadas]
        detalle = []
        if faltan:
            detalle.append(f"faltan {faltan}")
        if sobran:
            detalle.append(f"sobran {sobran}")
        if not detalle:
            detalle.append("el orden no coincide")
        r.errores.append("Columnas distintas al esquema: " + "; ".join(detalle))


def _columnas_requeridas(df, requeridas, r: Resultado):
    faltan = [c for c in requeridas if c not in df.columns]
    if faltan:
        r.errores.append(f"Faltan columnas requeridas: {faltan}")


def _id_unico(df, r: Resultado):
    col = config.COLUMNA_ID
    if col not in df.columns:
        r.errores.append(f"Falta la columna identificadora '{col}'")
        return
    # Conteo por identificador: cualquier id que aparezca más de una vez es un duplicado
    conteo = df[col].value_counts()
    repetidos = conteo[conteo > 1]
    duplicados = int((repetidos - 1).sum())
    if duplicados:
        r.errores.append(f"'{col}' tiene {duplicados} valores duplicados")
    vacios = int(_vacios(df[col]).sum())
    if vacios:
        r.errores.append(f"'{col}' tiene {vacios} valores vacíos")


def _sin_nulos(df, columnas, r: Resultado):
    for col in columnas:
        if col in df.columns:
            n = int(_vacios(df[col]).sum())
            if n:
                r.errores.append(f"'{col}' tiene {n} valores nulos o vacíos")


def _tipos_base(df, r: Resultado):
    """Tipos de las columnas originales que sigan presentes."""
    for col in ("vacantes", "pagina_origen"):
        if col in df.columns and df[col].dtype not in TIPOS_ENTEROS:
            r.errores.append(f"'{col}' debería ser entero y es {df[col].dtype}")
    if "remuneracion_pen" in df.columns and df["remuneracion_pen"].dtype not in TIPOS_NUMERICOS:
        r.errores.append(f"'remuneracion_pen' debería ser numérica y es {df['remuneracion_pen'].dtype}")
    for col in config.COLUMNAS_FECHA:
        if col in df.columns:
            malas = int(df[col].apply(_fecha_invalida).sum())
            if malas:
                r.errores.append(f"'{col}' tiene {malas} valores que no están en formato AAAA-MM-DD")


def _reglas_dominio(df, r: Resultado, como_error: bool):
    """Reglas de negocio. En el dataset crudo son advertencias; tras la limpieza, errores."""
    destino = r.errores if como_error else r.advertencias
    if "vacantes" in df.columns and df["vacantes"].dtype in TIPOS_NUMERICOS:
        BM = df["vacantes"] < 1
        n = int(BM.sum())
        if n:
            destino.append(f"{n} ofertas con menos de 1 vacante")
    if "remuneracion_pen" in df.columns and df["remuneracion_pen"].dtype in TIPOS_NUMERICOS:
        rem = df["remuneracion_pen"]
        n = int((rem <= 0).sum())
        if n:
            destino.append(f"{n} ofertas con remuneración menor o igual a 0")
        umbral = config.UMBRAL_REMUNERACION_MINIMA
        if umbral is not None:
            n = int((rem < umbral).sum())
            if n:
                destino.append(f"{n} ofertas con remuneración menor al umbral de S/ {umbral}")
        else:
            bajos = rem[rem < 1000].sort_values()
            if len(bajos):
                r.advertencias.append(
                    f"{len(bajos)} remuneraciones menores a S/ 1000 para revisar: "
                    f"{bajos.round(2).tolist()[:10]} (umbral aún no definido en config)"
                )
    if all(c in df.columns for c in config.COLUMNAS_FECHA):
        try:
            ini = pd.to_datetime(df["fecha_inicio_publicacion"])
            fin = pd.to_datetime(df["fecha_fin_publicacion"])
            n = int((fin < ini).sum())
        except (ValueError, TypeError):
            n = 0  # el formato incorrecto ya se reporta en _tipos_base
        if n:
            destino.append(f"{n} ofertas cuya fecha de fin es anterior a la de inicio")
    if "puesto" in df.columns:
        n = int(df["puesto"].apply(_es_solo_numero).sum())
        if n:
            destino.append(f"{n} ofertas cuyo puesto es solo un número (p. ej. '1')")


def _hash_reproducible(ruta: Path, r: Resultado):
    """Recalcula id_oferta_hash desde el texto crudo: prueba de linaje con la extracción."""
    texto = pd.read_csv(ruta, encoding=config.ENCODING, dtype=str, keep_default_na=False)
    if not all(c in texto.columns for c in config.CAMPOS_PRINCIPALES + [config.COLUMNA_ID]):
        return
    recalculado = texto.apply(_calcular_hash, axis=1)
    distintos = int((recalculado != texto[config.COLUMNA_ID]).sum())
    if distintos:
        r.errores.append(f"{distintos} filas cuyo id_oferta_hash no coincide con sus campos principales")


def _nulos_por_columna(df, r: Resultado, limite: float | None):
    if len(df) == 0:
        return
    nulos = df.isnull().sum() + (df == "").sum()
    for col in df.columns:
        prop = nulos[col] / len(df)
        if prop == 0:
            continue
        mensaje = f"'{col}' tiene {prop:.1%} de nulos"
        if limite is not None and prop > limite:
            r.errores.append(mensaje + f" (límite {limite:.0%})")
        else:
            r.advertencias.append(mensaje)


def _contra_diccionario(df, ruta_diccionario: Path, r: Resultado):
    if not ruta_diccionario.exists():
        r.advertencias.append(f"No existe {ruta_diccionario.name}; no se pudo comparar con el diccionario")
        return
    dic = pd.read_csv(ruta_diccionario, encoding=config.ENCODING)
    if dic.empty:
        r.advertencias.append(f"{ruta_diccionario.name} está vacío: falta documentar las variables finales")
        return
    documentadas = set(dic["variable"])
    sin_documentar = [c for c in df.columns if c not in documentadas]
    no_presentes = [v for v in dic["variable"] if v not in df.columns]
    if sin_documentar:
        r.errores.append(f"Columnas sin documentar en el diccionario: {sin_documentar}")
    if no_presentes:
        r.errores.append(f"Variables del diccionario que no están en el dataset: {no_presentes}")


# --- Contratos por etapa -----------------------------------------------------------

def validar_raw(ruta: Path = config.ARCHIVO_RAW) -> Resultado:
    """Etapa 1 · Ingestión: esquema exacto de 12 columnas, sin nulos, id único y reproducible."""
    df = cargar(ruta)
    r = Resultado("raw", Path(ruta), len(df), df.shape[1])
    _columnas_exactas(df, config.CAMPOS, r)
    _id_unico(df, r)
    _sin_nulos(df, config.CAMPOS, r)
    _tipos_base(df, r)
    _hash_reproducible(Path(ruta), r)
    _reglas_dominio(df, r, como_error=False)
    return r


def validar_limpio(ruta: Path = config.ARCHIVO_LIMPIO) -> Resultado:
    """Etapa 2 · Limpieza: campos principales completos y reglas de negocio cumplidas."""
    df = cargar(ruta)
    r = Resultado("limpio", Path(ruta), len(df), df.shape[1])
    _columnas_requeridas(df, [config.COLUMNA_ID] + config.CAMPOS_PRINCIPALES, r)
    _id_unico(df, r)
    _sin_nulos(df, config.CAMPOS_PRINCIPALES, r)
    _tipos_base(df, r)
    _reglas_dominio(df, r, como_error=True)
    return r


def validar_transformado(ruta: Path = config.ARCHIVO_TRANSFORMADO) -> Resultado:
    """Etapa 3 · Transformación: id único y nulos visibles por columna."""
    df = cargar(ruta)
    r = Resultado("transformado", Path(ruta), len(df), df.shape[1])
    _id_unico(df, r)
    _tipos_base(df, r)
    _nulos_por_columna(df, r, limite=None)
    return r


def validar_final(ruta: Path = config.ARCHIVO_FINAL) -> Resultado:
    """Etapa 4 · Dataset final: igual al diccionario final y ≤ 10 % de nulos por columna."""
    df = cargar(ruta)
    r = Resultado("final", Path(ruta), len(df), df.shape[1])
    _id_unico(df, r)
    _tipos_base(df, r)
    _nulos_por_columna(df, r, limite=LIMITE_NULOS_FINAL)
    _contra_diccionario(df, config.DICCIONARIO_FINAL, r)
    return r


ETAPAS = {
    "raw": (validar_raw, config.ARCHIVO_RAW),
    "limpio": (validar_limpio, config.ARCHIVO_LIMPIO),
    "transformado": (validar_transformado, config.ARCHIVO_TRANSFORMADO),
    "final": (validar_final, config.ARCHIVO_FINAL),
}

NOTEBOOK_DE = {
    "raw": "01_extraccion_talento_peru.ipynb",
    "limpio": "02_limpieza_datos.ipynb",
    "transformado": "03_transformacion_dataset_final.ipynb",
    "final": "04_feature_engineering.ipynb",
}


def validar(etapa: str, ruta: Path | None = None) -> Resultado:
    """Valida el archivo de una etapa ('raw', 'limpio', 'transformado' o 'final')."""
    if etapa not in ETAPAS:
        raise ValueError(f"Etapa desconocida '{etapa}'. Opciones: {list(ETAPAS)}")
    funcion, ruta_por_defecto = ETAPAS[etapa]
    ruta = Path(ruta) if ruta else ruta_por_defecto
    if not ruta.exists():
        raise FileNotFoundError(
            f"No existe el archivo de la etapa '{etapa}': {ruta}. "
            f"Ejecute primero notebooks/{NOTEBOOK_DE[etapa]}."
        )
    return funcion(ruta)


def cargar_entrada(etapa: str) -> pd.DataFrame:
    """Valida el archivo que entrega la etapa anterior y lo carga.

    Es la "puerta" de cada notebook: si la etapa anterior no cumple su contrato,
    el notebook se detiene antes de trabajar sobre datos incorrectos.
    """
    resultado = validar(etapa).exigir()
    return cargar(resultado.archivo)


def main(argv: list[str]) -> int:
    etapas = argv or list(ETAPAS)
    hubo_error = False
    for etapa in etapas:
        _, ruta = ETAPAS[etapa]
        if not ruta.exists():
            print(f"[--] {etapa}: aún no existe {ruta.relative_to(config.RAIZ)}")
            continue
        resultado = validar(etapa)
        print(resultado)
        hubo_error |= not resultado.ok
    return 1 if hubo_error else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
