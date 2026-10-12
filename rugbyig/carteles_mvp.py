"""Cartel "Jugador de la jornada" (post 4:5 o historia 9:16, en los 5 temas).

Tarjeta tipo MVP: foto de iSquad si tiene calidad (si no, el escudo en grande),
dorsal, posición, nombre, puntos y desglose, rival y resultado. El jugador es el
mismo que el del vídeo (rugbyig/videos/mvp.py: nota máxima del XV ideal).
"""
from __future__ import annotations

from pathlib import Path

from rugbyig.render.render import renderizar_slides
from rugbyig.videos.base import datos_jornada
from rugbyig.videos.mvp import ficha


def slide_mvp(datos: dict) -> dict:
    return {"tipo": "mvp", "clave": "mvp", "j": ficha(datos), "jornada_n": datos["jornada"]}


def renderizar_mvp(comp: str, grupo: str, destino: Path, jornada: int | None = None,
                   formato: str = "post", tema: str | None = None) -> list[Path]:
    """Pinta el cartel en `destino` (borra los .jpg que hubiera) y devuelve [ruta]."""
    datos = datos_jornada(comp, grupo, jornada)
    return renderizar_slides(datos, [slide_mvp(datos)], Path(destino), formato, tema)
