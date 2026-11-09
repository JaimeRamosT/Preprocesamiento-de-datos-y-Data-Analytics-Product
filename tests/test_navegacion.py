"""Prueba de punta a punta de la navegación con Selenium sobre un portal simulado.

Reproduce lo esencial del portal (tarjetas .cuadro-vacantes, indicador
"Página X de Y" y botón "Sig." que cambia la página con JavaScript) para
verificar el bucle de extracción sin depender de la conexión al portal real.
Se omite si no hay Chrome o Chromium instalado.
"""

import json
import shutil

import pandas as pd
import pytest

from src import config, extraccion

HAY_NAVEGADOR = any(shutil.which(n) for n in ("chromium", "chromium-browser", "google-chrome", "chrome"))

PORTAL_SIMULADO = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<span id="indicador"></span><div id="listado"></div>
<button id="frmLstOfertsLabo:j_idt56" onclick="siguiente()">Sig.</button>
<script>
const paginas = 3, porPagina = 3;
let actual = 1;
function tarjeta(n) {
  return `<div class="cuadro-vacantes">
    <div class="titulo-vacante"><label>PUESTO ${n}</label></div>
    <div class="nombre-entidad"><span class="detalle-sp">ENTIDAD ${n % 2}</span></div>
    <span class="sub-titulo">Ubicación:</span> <span class="detalle-sp">LIMA - LIMA</span>
    <span class="sub-titulo">Número de Convocatoria:</span> <span class="detalle-sp">CONV-${n}</span>
    <span class="sub-titulo">Cantidad de Vacantes:</span> <span class="detalle-sp">1</span>
    <span class="sub-titulo">Remuneración:</span> <span class="detalle-sp">S/. 3,000.00</span>
    <span class="sub-titulo">Fecha Inicio de Publicación:</span> <span class="detalle-sp">17/09/2026</span>
    <span class="sub-titulo">Fecha Fin de Publicación:</span> <span class="detalle-sp">30/09/2026</span>
  </div>`;
}
function pintar() {
  document.getElementById('indicador').textContent = `Página ${actual} de ${paginas}`;
  let html = '';
  for (let i = 0; i < porPagina; i++) html += tarjeta((actual - 1) * porPagina + i + 1);
  document.getElementById('listado').innerHTML = html;
  document.getElementById('frmLstOfertsLabo:j_idt56').disabled = actual === paginas;
}
function siguiente() { setTimeout(() => { actual += 1; pintar(); }, 200); }
pintar();
</script></body></html>"""


@pytest.fixture
def portal(tmp_path, monkeypatch):
    ruta = tmp_path / "portal.html"
    ruta.write_text(PORTAL_SIMULADO, encoding="utf-8")
    monkeypatch.setattr(config, "URL_FUENTE", ruta.as_uri())
    return tmp_path


@pytest.mark.skipif(not HAY_NAVEGADOR, reason="No hay Chrome/Chromium instalado")
def test_recorre_todas_las_paginas_y_guarda_estado(portal):
    archivo = portal / "talento_peru_ofertas_prueba.csv"
    estado = extraccion.extraer_listado(limite=100, pausa=0, archivo=archivo)

    df = pd.read_csv(archivo)
    assert len(df) == 9 and df["id_oferta_hash"].is_unique
    assert df["pagina_origen"].tolist() == [1, 1, 1, 2, 2, 2, 3, 3, 3]
    assert df.groupby("pagina_origen")["fecha_extraccion_utc"].nunique().eq(1).all()  # una marca por página
    assert estado["motivo_fin"] == "última página del portal"
    guardado = json.loads(extraccion.ruta_estado(archivo).read_text(encoding="utf-8"))
    assert guardado["paginas_recorridas"] == 3 and guardado["ofertas_en_archivo"] == 9


@pytest.mark.skipif(not HAY_NAVEGADOR, reason="No hay Chrome/Chromium instalado")
def test_respeta_el_limite_y_reanuda_sin_duplicar(portal):
    archivo = portal / "talento_peru_ofertas_prueba.csv"
    primera = extraccion.extraer_listado(limite=5, pausa=0, archivo=archivo)
    assert primera["motivo_fin"] == "límite alcanzado"
    assert len(pd.read_csv(archivo)) == 5

    segunda = extraccion.extraer_listado(limite=9, pausa=0, archivo=archivo)  # reanuda
    df = pd.read_csv(archivo)
    assert len(df) == 9 and df["id_oferta_hash"].is_unique
    assert segunda["ofertas_previas_en_archivo"] == 5 and segunda["ofertas_repetidas"] == 5
