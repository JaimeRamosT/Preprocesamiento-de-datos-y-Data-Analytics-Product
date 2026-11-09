# Cómo trabajar en este repositorio

Reglas acordadas para que el trabajo de los cinco integrantes se integre sin conflictos y el proyecto se pueda reproducir. Las revisa y hace cumplir el Integrante 1.

## Flujo de trabajo

1. Actualizar `main` antes de empezar: `git pull origin main`.
2. Trabajar en la rama propia:

   | Integrante | Rama | Archivos que modifica |
   |---|---|---|
   | 1 | `pipeline` | `src/`, `tests/`, `run_pipeline.py`, `README.md`, `docs/pipeline.md`, notebook 01 |
   | 2 | `limpieza` | notebook 02, `docs/decisiones/02_limpieza.csv`, `data/interim/talento_peru_limpio.csv` |
   | 3 | `transformacion` | notebook 03, `docs/diccionario_datos_final.*`, `data/interim/talento_peru_transformado.csv` |
   | 4 | `features` | notebook 04, filas nuevas del diccionario final, `data/processed/talento_peru_final.csv` |
   | 5 | `analisis` | notebook 05, `reports/figures/` |

   ```bash
   git checkout -b limpieza        # la primera vez
   git checkout limpieza           # las siguientes
   ```
3. Subir la rama y abrir un pull request hacia `main`. El Integrante 1 lo revisa, corre `python run_pipeline.py` y lo fusiona.

Si alguien necesita cambiar un archivo de otro integrante (por ejemplo, una ruta en `src/config.py`), lo pide en el pull request en vez de editarlo directamente.

## Commits

Un commit por cambio con sentido propio, con prefijo, ámbito y una descripción en presente:

```text
feat(limpieza): trata remuneraciones no plausibles
fix(extraccion): driver compatible con Windows
docs(readme): instrucciones de instalación en Colab
test(validacion): caso de ids duplicados
```

Prefijos: `feat` (funcionalidad o análisis nuevo), `fix` (corrección), `docs` (documentación), `data` (archivos de datos), `test` (pruebas), `refactor` (reorganización sin cambiar resultados). Nada de mensajes como "update", "cambios" o "final final". Cada integrante hace sus propios commits: son la evidencia del criterio "Aporte del integrante".

## Notebooks

- Conservar el encabezado, la celda de **Preparación** y la sección final de **Guardado y validación** de la plantilla.
- Leer y escribir solo con las rutas de `src/config.py` (`config.ARCHIVO_LIMPIO`, etc.); nunca rutas escritas a mano.
- Nunca modificar `data/raw/`.
- Registrar cada decisión con `registro.agregar(paso, accion, filas_afectadas, justificacion)`.
- Cada gráfico va seguido de una celda de texto que lo interpreta.
- Antes de cada commit: *Kernel → Restart & Run All*, para que las salidas guardadas sean las reales.

## Antes de abrir un pull request

- [ ] El notebook corre de principio a fin con *Restart & Run All*.
- [ ] La validación final del notebook muestra `[OK]`.
- [ ] Las decisiones quedaron en `docs/decisiones/`.
- [ ] Las variables nuevas o modificadas están en `docs/diccionario_datos_final.csv`.
- [ ] `python -m pytest` pasa.
