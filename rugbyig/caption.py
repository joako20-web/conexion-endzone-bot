"""Texto del post de Instagram a partir del JSON de la jornada."""
from __future__ import annotations

import yaml

from rugbyig.pipeline import CONFIG
from rugbyig.render import nombres


def texto_post(datos: dict) -> str:
    cfg = yaml.safe_load((CONFIG / "publicacion.yaml").read_text(encoding="utf-8"))
    grupo = "" if datos["grupo"] == "unico" else f" · Grupo {datos['grupo']}"
    lineas = [f"🏉 {datos['nombre']}{grupo} · Jornada {datos['jornada']}", ""]

    for p in datos["partidos"]:
        loc, vis = nombres.equipo_corto(p["local"]), nombres.equipo_corto(p["visitante"])
        if p["puntos_local"] is None:
            lineas.append(f"{loc} – {vis} (sin resultado)")
        else:
            lineas.append(f"{loc} {p['puntos_local']}-{p['puntos_visitante']} {vis}")
    lineas.append("")

    if datos.get("xv_ideal"):
        mvp = max(datos["xv_ideal"].values(), key=lambda x: x["nota"])
        lineas.append(
            f"⭐ Mejor jugador: {nombres.jugador(mvp['nombre'])['completo']} "
            f"({nombres.equipo_corto(mvp['equipo'])})"
        )
    if datos["anotadores"]:
        top = datos["anotadores"][0]
        lineas.append(
            f"🎯 Máximo anotador: {nombres.jugador(top['nombre'])['completo']}, {top['puntos']} pts"
        )
    if datos["clasificacion"]:
        lider = datos["clasificacion"][0]
        lineas.append(f"🔝 Líder: {nombres.equipo_corto(lider['equipo'])} con {lider['pt']} puntos")

    partes = ["resultados"]
    if datos["anotadores"]:
        partes.append("anotadores")
    if datos.get("xv_ideal"):
        partes.append("el XV ideal")
    partes += ["la clasificación", "la próxima jornada"]
    lineas += ["", f"Desliza para ver {', '.join(partes[:-1])} y {partes[-1]} ➡️", ""]

    etiquetas = cfg["hashtags"].get(datos["competicion"], []) + cfg["hashtags"]["comunes"]
    lineas.append(" ".join(etiquetas))
    return "\n".join(lineas)
