"""Registro de decisiones de preprocesamiento.

Cada etapa anota qué hizo, a cuántas filas afectó y por qué. El registro se
guarda en ``docs/decisiones/<etapa>.csv`` y alimenta la sección de
preprocesamiento del informe y ``docs/pipeline.md``: así toda decisión queda
documentada y sustentada, que es lo que pide la rúbrica.

Ejemplo::

    from src.registro import Registro
    registro = Registro("02_limpieza")
    registro.agregar(
        paso="Valores atípicos",
        accion="Se eliminaron ofertas con remuneración menor al umbral definido",
        filas_afectadas=4,
        justificacion="Explicar por qué esos montos no son plausibles para un sueldo mensual",
    )
    registro.guardar()
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src import config

DIR_DECISIONES = config.DIR_DOCS / "decisiones"
COLUMNAS = ["etapa", "n", "paso", "accion", "filas_afectadas", "justificacion", "fecha"]


class Registro:
    def __init__(self, etapa: str):
        self.etapa = etapa
        self.filas: list[dict] = []

    def agregar(self, paso: str, accion: str, filas_afectadas: int | None, justificacion: str) -> None:
        self.filas.append({
            "etapa": self.etapa,
            "n": len(self.filas) + 1,
            "paso": paso,
            "accion": accion,
            "filas_afectadas": filas_afectadas,
            "justificacion": justificacion,
            "fecha": date.today().isoformat(),
        })

    def tabla(self) -> pd.DataFrame:
        return pd.DataFrame(self.filas, columns=COLUMNAS)

    @property
    def ruta(self):
        return DIR_DECISIONES / f"{self.etapa}.csv"

    def guardar(self):
        """Reescribe el registro de la etapa (cada ejecución del notebook lo regenera)."""
        DIR_DECISIONES.mkdir(parents=True, exist_ok=True)
        self.tabla().to_csv(self.ruta, index=False, encoding=config.ENCODING)
        return self.ruta


def todas_las_decisiones() -> pd.DataFrame:
    """Une los registros de todas las etapas (para el informe)."""
    archivos = sorted(DIR_DECISIONES.glob("*.csv")) if DIR_DECISIONES.exists() else []
    if not archivos:
        return pd.DataFrame(columns=COLUMNAS)
    return pd.concat([pd.read_csv(a, encoding=config.ENCODING) for a in archivos], ignore_index=True)
