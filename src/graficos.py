"""Utilidades para que todos los gráficos se guarden igual en reports/figures/."""

from __future__ import annotations

import matplotlib.pyplot as plt

from src import config


def guardar_figura(nombre: str, fig=None, dpi: int = 200):
    """Guarda la figura actual (o ``fig``) como reports/figures/<nombre>.png."""
    config.DIR_FIGURAS.mkdir(parents=True, exist_ok=True)
    fig = fig or plt.gcf()
    ruta = config.DIR_FIGURAS / f"{nombre}.png"
    fig.savefig(ruta, dpi=dpi, bbox_inches="tight")
    return ruta
