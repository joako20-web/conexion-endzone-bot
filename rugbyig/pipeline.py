"""Junta los datos de una jornada en un JSON editable (data/.../jNN.json)."""
from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

import yaml

from rugbyig.core import estadisticas as E
from rugbyig.scraper.isquad import ISquad

FOTO_MIN_PX = 600


def elegir_foto_portada(candidatos: list[E.LineaJugador], cliente: ISquad) -> dict | None:
    """Primer candidato con una foto de calidad suficiente para la portada.

    Muchas fotos de iSquad son de carnet (153 px); esas no sirven a sangre.
    """
    from PIL import Image

    vistos = set()
    for ln in candidatos:
        if not ln.foto or ln.foto in vistos:
            continue
        vistos.add(ln.foto)
        try:
            ancho, alto = Image.open(io.BytesIO(cliente.imagen(ln.foto))).size
        except Exception:
            continue
        if min(ancho, alto) >= FOTO_MIN_PX:
            return {"url": ln.foto, "jugador": ln.nombre, "equipo": ln.equipo, "motivo": ""}
    return None

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
DATA = RAIZ / "data"


def cargar_config() -> dict:
    return yaml.safe_load((CONFIG / "competiciones.yaml").read_text(encoding="utf-8"))


def ruta_jornada(comp: str, grupo: str, jornada: int) -> Path:
    temporada = cargar_config()["temporada"].replace("/", "-")
    return DATA / temporada / comp / grupo / f"j{jornada:02d}.json"


def _partido(p) -> dict:
    d = asdict(p)
    d["fecha"] = p.fecha.isoformat() if p.fecha else None
    return d


def jornadas_jugadas(comp: str, grupo: str = "unico", cliente: ISquad | None = None) -> list[int]:
    cfg = cargar_config()["competiciones"][comp]
    cliente = cliente or ISquad()
    id_grupo = cfg["grupos"][grupo]
    equipos = {f.equipo for f in cliente.clasificacion(id_grupo)}
    competicion = cliente.competicion(id_grupo).filtrar(equipos)
    return sorted({p.jornada for p in competicion.partidos if p.jugado})


def preparar_jornada(
    comp: str, grupo: str = "unico", jornada: int | None = None, cliente: ISquad | None = None
) -> Path:
    cfg = cargar_config()["competiciones"][comp]
    id_grupo = cfg["grupos"][grupo]
    cliente = cliente or ISquad()

    clasificacion = cliente.clasificacion(id_grupo)
    competicion = cliente.competicion(id_grupo).filtrar({f.equipo for f in clasificacion})
    jornada = jornada or competicion.ultima_jornada_jugada()
    if jornada is None:
        raise RuntimeError(f"{comp}/{grupo}: aún no hay jornadas jugadas")

    partidos = competicion.jornada(jornada)
    lineas: list[E.LineaJugador] = []
    pendientes = []
    for p in partidos:
        if not p.jugado:
            pendientes.append(p.id)
            continue
        acta = cliente.acta(p.id)
        if acta.marcador_por_eventos() != (p.puntos_local, p.puntos_visitante):
            # Acta incompleta: el marcador vale, pero no sus estadísticas.
            pendientes.append(p.id)
            continue
        lineas += E.lineas_partido(p, acta)

    xv = E.xv_ideal(lineas) if cfg.get("xv_ideal") and lineas else {}
    mejores = sorted(xv.values(), key=lambda ln: -ln.nota) + E.anotadores(lineas, 5)
    foto = elegir_foto_portada(mejores, cliente) if cargar_config().get("foto_portada_auto") else None
    if foto:
        foto["motivo"] = (
            "Mejor jugador de la jornada"
            if xv and foto["jugador"] == mejores[0].nombre
            else "Protagonista de la jornada"
        )

    siguiente = competicion.jornada(jornada + 1)
    datos = {
        "competicion": comp,
        "nombre": cfg["nombre"],
        "grupo": grupo,
        "temporada": cargar_config()["temporada"],
        "jornada": jornada,
        "partidos": [_partido(p) for p in partidos],
        "actas_pendientes": pendientes,
        "anotadores": [asdict(x) for x in E.anotadores(lineas, 10)],
        "ensayadores": [asdict(x) for x in E.maximos_ensayadores(lineas, 5)],
        "xv_ideal": {str(d): asdict(ln) for d, ln in xv.items()} or None,
        "foto_portada": foto,
        "candidatos_xv": sorted(
            (asdict(ln) for ln in lineas if 1 <= ln.dorsal <= 15),
            key=lambda x: (x["dorsal"], -x["nota"]),
        ),
        "clasificacion": [asdict(f) for f in clasificacion],
        "escudos": {f.equipo: f.escudo for f in clasificacion if f.escudo},
        "temporada_anotadores": [
            asdict(j)
            for j in sorted(competicion.jugadores, key=lambda j: (-j.puntos, -j.ensayos))[:10]
        ],
        "temporada_ensayadores": [
            asdict(j)
            for j in sorted(competicion.jugadores, key=lambda j: (-j.ensayos, -j.puntos))[:5]
        ],
        "proxima_jornada": {
            "numero": jornada + 1,
            "partidos": [_partido(p) for p in siguiente],
        }
        if siguiente
        else None,
    }

    ruta = ruta_jornada(comp, grupo, jornada)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    previo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    if previo.get("foto_portada", {}) and previo["foto_portada"].get("archivo"):
        datos["foto_portada"] = previo["foto_portada"]  # foto puesta a mano
    if previo.get("xv_editado"):
        # No pisar los cambios manuales del XV al regenerar.
        datos["xv_ideal"] = previo["xv_ideal"]
        datos["xv_editado"] = True
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta
