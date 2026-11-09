"""Pruebas de los contratos de datos: un archivo válido pasa y uno roto se detiene."""

import pandas as pd
import pytest

from src import config, validacion


def test_dataset_inicial_cumple_el_contrato_raw():
    resultado = validacion.validar("raw")
    assert resultado.ok, resultado
    assert resultado.filas == 1010 and resultado.columnas == 12
    # Las anomalías conocidas de la Parte 1 quedan como advertencias, no como errores
    assert any("remuneraciones menores" in a for a in resultado.advertencias)


def test_duplicados_y_nulos_rompen_el_contrato_limpio(tmp_path):
    df = pd.read_csv(config.ARCHIVO_RAW).head(5)
    df.loc[1, "id_oferta_hash"] = df.loc[0, "id_oferta_hash"]
    df.loc[2, "entidad"] = ""
    df.loc[3, "remuneracion_pen"] = 0
    ruta = tmp_path / "limpio.csv"
    df.to_csv(ruta, index=False)

    resultado = validacion.validar("limpio", ruta)
    assert not resultado.ok
    texto = "\n".join(resultado.errores)
    assert "duplicados" in texto and "'entidad'" in texto and "menor o igual a 0" in texto
    with pytest.raises(validacion.ValidacionError):
        resultado.exigir()


def test_columnas_cambiadas_rompen_el_contrato_raw(tmp_path):
    df = pd.read_csv(config.ARCHIVO_RAW).drop(columns=["fuente_url"])
    ruta = tmp_path / "raw.csv"
    df.to_csv(ruta, index=False)
    assert not validacion.validar("raw", ruta).ok
