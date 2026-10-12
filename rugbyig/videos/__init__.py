"""Vídeos verticales para Reels con motion graphics (Remotion, en video/).

Cada plantilla es un módulo de este paquete con:
- `COMPOSICION`: id de la composición en video/src/Root.tsx
- `props(...)`: construye sus props a partir de los datos (sin IA, sin red salvo escudos)
y se registra en PLANTILLAS con su nombre para el bot y cómo se obtienen sus datos.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from rugbyig.rutas import RAIZ
from rugbyig.videos import base, final, jornada


@dataclass(frozen=True)
class Plantilla:
    clave: str
    nombre: str  # botón del bot
    composicion: str
    # (comp, grupo, jornada, extra) -> props
    construir: Callable[..., dict]
    por_liga: bool = True  # aparece en el menú 🎬 de cada liga


def _jornada(comp: str, grupo: str, jornada_: int | None, **_) -> dict:
    props = jornada.props(base.datos_jornada(comp, grupo, jornada_))
    if not props["partidos"]:
        raise RuntimeError(f"la jornada {props['jornada']} aún no tiene resultados")
    return props


PLANTILLAS: dict[str, Plantilla] = {p.clave: p for p in [
    Plantilla("jornada", "📊 Resultados de la jornada", jornada.COMPOSICION, _jornada),
    # por partido: reel(comp, grupo, jornada, tipo="final", id_partido=17648)
    Plantilla("final", "🏉 Así fue el partido", final.COMPOSICION, final.construir, por_liga=False),
]}


def reel(comp: str, grupo: str = "unico", jornada: int | None = None, tipo: str = "jornada",
         salida: Path | None = None, **extra) -> Path:
    """Genera el vídeo `tipo` y devuelve la ruta del MP4."""
    p = PLANTILLAS[tipo]
    props = p.construir(comp, grupo, jornada, **extra)
    sufijo = f"_p{extra['id_partido']}" if extra.get("id_partido") else ""
    salida = salida or RAIZ / "out" / f"reel_{tipo}_{comp}_{grupo}_j{props.get('jornada', 0):02d}{sufijo}.mp4"
    return base.renderizar(p.composicion, props, salida)
