"""Ejecuta el pipeline completo: cada notebook en orden y la validación de su salida.

Uso (desde la raíz del repositorio, con el entorno virtual activado):

    python run_pipeline.py                  # etapas 02 a 05 sobre el dataset inicial
    python run_pipeline.py --desde 03       # retoma desde una etapa
    python run_pipeline.py --hasta 02       # se detiene en una etapa
    python run_pipeline.py --con-01         # incluye el notebook 01 (extracción desactivada)
    python run_pipeline.py --solo-validar   # no ejecuta nada, solo valida los archivos existentes
    python run_pipeline.py --extraer --limite 30   # genera un corte NUEVO antes (requiere Chrome)

Los notebooks se ejecutan en su lugar y se guardan con sus salidas, para que en
GitHub se vean los resultados reales. Si un notebook falla o su salida no cumple
el contrato de datos, el pipeline se detiene e indica dónde.
"""

from __future__ import annotations

import argparse
import re
import sys
import time

from src import config, validacion

# (código, notebook, etapa de validación de su salida)
ETAPAS = [
    ("01", "01_extraccion_talento_peru.ipynb", "raw"),
    ("02", "02_limpieza_datos.ipynb", "limpio"),
    ("03", "03_transformacion_dataset_final.ipynb", "transformado"),
    ("04", "04_feature_engineering.ipynb", "final"),
    ("05", "05_analisis_exploratorio.ipynb", None),
]


def ejecutar_notebook(nombre: str, timeout: int = 1800) -> None:
    import nbformat
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError

    ruta = config.DIR_NOTEBOOKS / nombre
    nb = nbformat.read(ruta, as_version=4)
    cliente = NotebookClient(
        nb, timeout=timeout, kernel_name="python3",
        resources={"metadata": {"path": str(config.DIR_NOTEBOOKS)}},
    )
    try:
        cliente.execute()
    except CellExecutionError as error:
        nbformat.write(nb, ruta)  # guarda hasta donde llegó, con el error visible
        ultima_linea = re.sub(r"\x1b\[[0-9;]*m", "", str(error).strip().splitlines()[-1])
        raise RuntimeError(f"Falló una celda de {nombre}: {ultima_linea}") from None
    nbformat.write(nb, ruta)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--desde", default="02", choices=[c for c, _, _ in ETAPAS])
    parser.add_argument("--hasta", default="05", choices=[c for c, _, _ in ETAPAS])
    parser.add_argument("--con-01", action="store_true", help="ejecuta también el notebook 01")
    parser.add_argument("--solo-validar", action="store_true", help="solo valida los archivos existentes")
    parser.add_argument("--extraer", action="store_true", help="genera un corte nuevo antes de empezar")
    parser.add_argument("--limite", type=int, default=1010, help="ofertas del corte nuevo")
    parser.add_argument("--pausa", type=float, default=2, help="segundos entre páginas")
    args = parser.parse_args()

    if args.solo_validar:
        return validacion.main([])

    if args.extraer:
        from src import extraccion
        print("== Extracción de un corte nuevo ==")
        estado = extraccion.extraer_listado(args.limite, args.pausa)
        validacion.validar("raw", config.DIR_RAW / estado["archivo"]).exigir()
        print("El corte nuevo NO reemplaza al dataset inicial: para analizarlo, cambie "
              "config.ARCHIVO_RAW.\n")

    desde = "01" if args.con_01 else args.desde
    seleccion = [e for e in ETAPAS if desde <= e[0] <= args.hasta]

    print("== Validación de la entrada ==")
    validacion.validar("raw").exigir()

    for codigo, notebook, etapa in seleccion:
        print(f"\n== Etapa {codigo}: {notebook} ==")
        inicio = time.time()
        try:
            ejecutar_notebook(notebook)
        except RuntimeError as error:
            print(f"[DETENIDO] {error}")
            print(f"Abra notebooks/{notebook} para ver la celda con error.")
            return 1
        print(f"Ejecutado en {time.time() - inicio:.1f} s")
        if etapa:
            try:
                validacion.validar(etapa).exigir()
            except validacion.ValidacionError as error:
                print(f"[DETENIDO] {error}")
                return 1

    print("\nPipeline completo: todas las etapas cumplen su contrato de datos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
