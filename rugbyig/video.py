"""Reel de resultados de una jornada (vídeo vertical con motion graphics).

Python prepara las props (datos, escudos, colores del tema) y los efectos de sonido;
la animación vive en video/ (Remotion) y se renderiza con `npx remotion render`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from rugbyig import sonido
from rugbyig.core.estadisticas import POSICIONES
from rugbyig.pipeline import cargar_config, preparar_jornada
from rugbyig.render import nombres
from rugbyig.render import render as R
from rugbyig.rutas import CONFIG, RAIZ

VIDEO = RAIZ / "video"
PUBLICO = VIDEO / "public"
TEMAS_CSS = Path(R.__file__).parent / "templates" / "temas.css"
# Familias de cada tema para el vídeo (titulares/números y texto)
FUENTES = {"tele": ("Oswald", "Roboto Condensed")}


def colores_tema(tema: str) -> dict:
    """Variables CSS (--fondo, --acento...) del bloque `.tema-<tema> {` de temas.css."""
    css = TEMAS_CSS.read_text(encoding="utf-8")
    bloque = re.search(r"\.tema-" + tema + r"\s*\{(.*?)\}", css, re.S)
    if not bloque:
        return {}
    return {k: v.strip() for k, v in re.findall(r"--([\w-]+):\s*([^;]+);", bloque.group(1))
            if v.strip().startswith("#")}


def _equipo(equipo: str, escudos: dict, puntos: int | None = None, gana: bool = False) -> dict:
    return {"nombre": nombres.equipo_corto(equipo), "abr": nombres.equipo_abr(equipo),
            "escudo": R.escudo_equipo(equipo, escudos), "puntos": puntos, "gana": gana}


def props_jornada(datos: dict, tema: str = "tele") -> dict:
    escudos = datos["escudos"]
    partidos = []
    for p in datos["partidos"]:
        if p.get("puntos_local") is None:
            continue
        pl, pv = p["puntos_local"], p["puntos_visitante"]
        partidos.append({"local": _equipo(p["local"], escudos, pl, pl > pv),
                         "visitante": _equipo(p["visitante"], escudos, pv, pv > pl)})

    dato = next(iter(datos.get("datos_jornada") or []), None)
    gancho = {"numero": dato["numero"], "unidad": dato["unidad"], "titular": dato["titular"],
              "escudo": R.escudo_equipo(dato["equipo"], escudos) if dato.get("equipo") else ""} if dato else None

    mvp = None
    candidatos = list((datos.get("xv_ideal") or {}).values()) or datos.get("anotadores") or []
    if candidatos:
        m = max(candidatos, key=lambda x: (x.get("nota", 0), x["puntos"]))
        j = nombres.jugador(m["nombre"])
        mvp = {"nombre": j["nombre"], "apellidos": j["apellidos"], "equipo": nombres.equipo_corto(m["equipo"]),
               "escudo": R.escudo_equipo(m["equipo"], escudos), "posicion": POSICIONES.get(m.get("dorsal"), ""),
               "dorsal": m.get("dorsal"), "puntos": m["puntos"],
               "stats": [{"valor": m[k], "texto": t} for k, t in
                         (("ensayos", "ensayos"), ("conversiones", "transf."), ("golpes", "golpes"), ("drops", "drops"))
                         if m.get(k)]}

    filas, leyenda = R.con_zonas(datos["clasificacion"], datos["competicion"], datos["grupo"])
    top = [{"pos": f["posicion"], "nombre": nombres.equipo_corto(f["equipo"]), "escudo": R.escudo_equipo(f["equipo"], escudos),
            "pt": f["pt"], "pj": f["pj"], "zona": f["zona"]} for f in filas[:4]]
    tras = max((f["pj"] for f in datos["clasificacion"]), default=datos["jornada"])

    cfg = cargar_config()["competiciones"][datos["competicion"]]
    marca = yaml.safe_load((CONFIG / "marca.yaml").read_text(encoding="utf-8"))
    logo = RAIZ / marca["logo"]
    tit, txt = FUENTES.get(tema, FUENTES["tele"])
    return {
        "competicion": cfg["nombre"], "corto": cfg.get("corto", cfg["nombre"]), "jornada": datos["jornada"],
        "temporada": datos["temporada"], "handle": marca["handle"],
        "logo": R._data_uri(logo.read_bytes(), "image/png"),
        "tema": colores_tema(tema), "fuenteTitulo": tit, "fuenteTexto": txt,
        "gancho": gancho, "partidos": partidos[:5], "mvp": mvp,
        "top": top, "trasJornada": tras, "zonaTop": leyenda[0]["texto"] if leyenda else "",
    }


def copiar_fuentes(familias: tuple[str, ...]) -> list[dict]:
    """Copia las woff2 del tema a video/public/fuentes y devuelve su lista para loadFont."""
    origen = RAIZ / "assets" / "fuentes"
    destino = PUBLICO / "fuentes"
    destino.mkdir(parents=True, exist_ok=True)
    lista = []
    for f in json.loads((origen / "fuentes.json").read_text(encoding="utf-8")):
        if f["familia"] in familias:
            shutil.copy2(origen / f["archivo"], destino / f["archivo"])
            lista.append({"familia": f["familia"], "peso": f["peso"], "archivo": f"fuentes/{f['archivo']}",
                          "rango": f["rango"]})
    return lista


def reel(comp: str, grupo: str = "unico", jornada: int | None = None, tema: str = "tele",
         salida: Path | None = None) -> Path:
    from rugbyig.pipeline import ruta_jornada

    # Jornada ya guardada: se usa tal cual (su clasificación es la de aquel momento)
    ruta = ruta_jornada(comp, grupo, jornada) if jornada else None
    if not (ruta and ruta.exists()):
        ruta = preparar_jornada(comp, grupo, jornada)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    props = props_jornada(datos, tema)
    props["fuentes"] = copiar_fuentes((props["fuenteTitulo"], props["fuenteTexto"]))
    sonido.generar(PUBLICO / "sfx")
    ruta_props = PUBLICO / "props.json"
    ruta_props.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    salida = salida or RAIZ / "out" / f"reel_{comp}_j{datos['jornada']:02d}.mp4"
    salida.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["npx", "remotion", "render", "ReelJornada", str(salida), f"--props={ruta_props}",
                    "--codec=h264", "--crf=16", "--audio-bitrate=320k"], cwd=VIDEO, check=True)
    return salida
