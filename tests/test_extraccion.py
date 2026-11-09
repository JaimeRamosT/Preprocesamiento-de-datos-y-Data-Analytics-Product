"""Pruebas del parseo sin conexión: una tarjeta con la estructura HTML del portal
debe producir exactamente la fila (y el hash) del dataset inicial."""

from pathlib import Path

import pandas as pd
import pytest

from src import config, extraccion

TARJETA_COMPLETA = """
<div class="cuadro-vacantes">
  <div class="titulo-vacante"><label>ESPECIALISTA&nbsp;LEGAL </label></div>
  <div class="nombre-entidad"><span class="detalle-sp">PODER JUDICIAL</span></div>
  <span class="sub-titulo">Ubicación:</span> <span class="detalle-sp">JUNIN - EL TAMBO</span>
  <span class="sub-titulo">Número de Convocatoria:</span>
  <span class="detalle-sp">D.LEG 1057 - DETERMINADO   (NECESIDAD TRANSITORIA)-093</span>
  <span class="sub-titulo">Cantidad de Vacantes:</span> <span class="detalle-sp">1</span>
  <span class="sub-titulo">Remuneración:</span> <span class="detalle-sp">S/. 5,670.00</span>
  <span class="sub-titulo">Fecha Inicio de Publicación:</span> <span class="detalle-sp">18/09/2026</span>
  <span class="sub-titulo">Fecha Fin de Publicación:</span> <span class="detalle-sp">01/10/2026</span>
</div>
"""

TARJETA_SIN_REMUNERACION = """
<div class="cuadro-vacantes">
  <div class="titulo-vacante"><label>ASISTENTE</label></div>
  <div class="nombre-entidad"><span class="detalle-sp">ENTIDAD X</span></div>
  <span class="sub-titulo">Ubicación:</span> <span class="detalle-sp">LIMA - LIMA</span>
  <span class="sub-titulo">Número de Convocatoria:</span> <span class="detalle-sp">001</span>
  <span class="sub-titulo">Cantidad de Vacantes:</span> <span class="detalle-sp">2</span>
  <span class="sub-titulo">Fecha Inicio de Publicación:</span> <span class="detalle-sp">18/09/2026</span>
  <span class="sub-titulo">Fecha Fin de Publicación:</span> <span class="detalle-sp">01/10/2026</span>
</div>
"""

PAGINA = f"<html><body><span>Página 1 de 453</span>{TARJETA_COMPLETA}{TARJETA_SIN_REMUNERACION}</body></html>"


def test_tarjeta_reproduce_fila_y_hash_del_dataset_inicial():
    ofertas, incompletas = extraccion.extraer_pagina(PAGINA, 1, "2026-09-18T05:58:55+00:00")
    assert incompletas == 1
    assert len(ofertas) == 1
    oferta = ofertas[0]
    assert list(oferta) == config.CAMPOS
    assert oferta["puesto"] == "ESPECIALISTA LEGAL"
    assert oferta["numero_convocatoria"] == "D.LEG 1057 - DETERMINADO (NECESIDAD TRANSITORIA)-093"
    assert oferta["remuneracion_pen"] == 5670.0
    assert oferta["fecha_fin_publicacion"] == "2026-10-01"
    # Mismo identificador que la primera fila de data/raw/talento_peru_ofertas.csv
    assert oferta["id_oferta_hash"] == "1af30dbb2f0f39e7d0c908cf"


def test_indicador_de_pagina():
    assert extraccion.obtener_pagina(PAGINA) == (1, 453)


@pytest.mark.parametrize("texto, esperado", [("S/. 7,000.00", 7000.0), ("2714.19", 2714.19), ("sin dato", None)])
def test_convertir_numero(texto, esperado):
    assert extraccion.convertir_numero(texto) == esperado


def test_convertir_fecha():
    assert extraccion.convertir_fecha(" 22/09/2026 ") == "2026-09-22"
    assert extraccion.convertir_fecha("2026-09-22") is None


def test_hash_reproduce_todo_el_dataset_inicial():
    texto = pd.read_csv(config.ARCHIVO_RAW, dtype=str, keep_default_na=False)
    recalculado = texto.apply(lambda fila: extraccion.calcular_hash(fila.to_dict()), axis=1)
    assert (recalculado == texto["id_oferta_hash"]).all()


def test_no_sobrescribe_el_dataset_inicial():
    with pytest.raises(ValueError):
        extraccion.extraer_listado(limite=10, archivo=config.ARCHIVO_RAW)


def test_rutas_de_corte_y_estado():
    corte = extraccion.ruta_corte()
    assert corte.parent == config.DIR_RAW
    assert extraccion.ruta_estado(Path("talento_peru_ofertas_20261109.csv")).name == "talento_peru_estado_20261109.json"
