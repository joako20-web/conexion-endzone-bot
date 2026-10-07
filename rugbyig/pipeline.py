"""Junta los datos de una jornada en un JSON editable (data/.../jNN.json)."""
from __future__ import annotations

import io
import json
from dataclasses import asdict
from pathlib import Path

import yaml

from rugbyig.core import datos as D
from rugbyig.models import JugadorTemporada
from rugbyig.core import rankings as R
from rugbyig.core import estadisticas as E
from rugbyig.scraper.isquad import ISquad, cliente_para

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

from rugbyig.rutas import CONFIG, DATA, RAIZ  # noqa: F401  (se reexportan)


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
    cliente = cliente or cliente_para(cfg)
    id_grupo = cfg["grupos"][grupo]
    equipos = {f.equipo for f in cliente.clasificacion(id_grupo)}
    competicion = cliente.competicion(id_grupo).filtrar(id_grupo, equipos)
    return sorted({p.jornada for p in competicion.partidos if p.jugado})


def _fila_resumen(ln: E.LineaJugador) -> list:
    """[nombre, equipo, puntos, ensayos, conversiones, golpes, drops, amarillas, rojas, dorsal]"""
    rojas = sum(t in ("roja", "roja20") for t in ln.tarjetas)
    return [ln.nombre, ln.equipo, ln.puntos, ln.ensayos, ln.conversiones, ln.golpes, ln.drops,
            ln.tarjetas.count("amarilla"), rojas, ln.dorsal]


def jugadores_desde_resumen(resumen: dict[str, list], todos: bool = False) -> list[JugadorTemporada]:
    """Tabla de temporada (puntos, ensayos, tarjetas) sumando el resumen de partidos."""
    acum: dict[tuple[str, str], JugadorTemporada] = {}
    for filas in resumen.values():
        for f in filas:
            nombre, equipo, puntos, ensayos = f[0], f[1], f[2], f[3]
            j = acum.setdefault((nombre, equipo), JugadorTemporada(None, nombre, equipo, 0, 0, 0, 0, 0))
            j.pj += 1  # partidos convocado
            j.puntos += puntos
            j.ensayos += ensayos
            if len(f) > 8:
                j.amarillas += f[7]
                j.rojas += f[8]
    return list(acum.values()) if todos else [j for j in acum.values() if j.puntos or j.ensayos]


def actualizar_resumen(comp: str, grupo: str) -> dict[str, list]:
    """Rehace/completa el resumen de partidos de una competición (actas en caché)."""
    cfg = cargar_config()["competiciones"][comp]
    cliente = cliente_para(cfg)
    id_grupo = cfg["grupos"][grupo]
    equipos = {f.equipo for f in cliente.clasificacion(id_grupo)}
    competicion = cliente.competicion(id_grupo).filtrar(id_grupo, equipos)
    return resumen_temporada(comp, grupo, competicion, cliente)


def resumen_temporada(comp: str, grupo: str, competicion, cliente: ISquad) -> dict[str, list]:
    """Estadísticas de cada jugador en cada partido jugado de la temporada.

    Se guarda en data/ (se commitea) para no volver a bajar las actas antiguas.
    Formato: {id_partido: [[nombre, equipo, puntos, ensayos, conversiones, golpes,
    drops, amarillas, rojas, dorsal], ...]} — solo jugadores convocado.
    Si el fichero tiene el formato antiguo ([nombre, equipo, puntos, ensayos]) se
    regenera (las actas están en caché).
    """
    ruta = ruta_jornada(comp, grupo, 0).with_name("resumen_partidos.json")
    resumen = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    # Formato antiguo (menos campos, o solo anotadores: pocas filas por partido) -> rehacer
    if any(len(j) != R.CAMPOS_RESUMEN for jugadores in resumen.values() for j in jugadores) or (
            resumen and max(len(js) for js in resumen.values()) < 26):
        resumen = {}  # formato antiguo
    for p in competicion.partidos:
        if not p.jugado or str(p.id) in resumen:
            continue
        acta = cliente.acta(p.id)
        if acta.marcador_por_eventos() != (p.puntos_local, p.puntos_visitante):
            continue  # acta incompleta: se reintenta la próxima vez
        resumen[str(p.id)] = [
            _fila_resumen(ln) for ln in E.lineas_partido(p, acta)  # todos los convocados
        ]
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")
    return resumen


def preparar_jornada(
    comp: str, grupo: str = "unico", jornada: int | None = None, cliente: ISquad | None = None
) -> Path:
    cfg = cargar_config()["competiciones"][comp]
    id_grupo = cfg["grupos"][grupo]
    cliente = cliente or cliente_para(cfg)

    clasificacion = cliente.clasificacion(id_grupo)
    competicion = cliente.competicion(id_grupo).filtrar(id_grupo, {f.equipo for f in clasificacion})
    jornada = jornada or competicion.ultima_jornada_jugada()
    if jornada is None:
        raise RuntimeError(f"{comp}/{grupo}: aún no hay jornadas jugadas")

    partidos = competicion.jornada(jornada)
    lineas: list[E.LineaJugador] = []
    pendientes = []
    actas_jornada = []
    for p in partidos:
        if not p.jugado:
            continue  # aplazado o sin resultado: sale como "Sin resultado", no es un acta pendiente
        acta = cliente.acta(p.id)
        if acta.marcador_por_eventos() != (p.puntos_local, p.puntos_visitante):
            # Acta incompleta: el marcador vale, pero no sus estadísticas.
            pendientes.append(p.id)
            continue
        lineas += E.lineas_partido(p, acta)
        actas_jornada.append((_partido(p), [asdict(e) for e in acta.eventos]))
    resumen = resumen_temporada(comp, grupo, competicion, cliente)
    # MatchReady no publica tabla de jugadores: se calcula con las actas de la temporada
    jugadores_temporada = competicion.jugadores or jugadores_desde_resumen(resumen)

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
        "partidos_temporada": [_partido(p) for p in competicion.partidos if p.jugado],
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
            for j in sorted(jugadores_temporada, key=lambda j: (-j.puntos, -j.ensayos))[:10]
        ],
        "temporada_ensayadores": [
            asdict(j)
            for j in sorted(jugadores_temporada, key=lambda j: (-j.ensayos, -j.puntos))[:5]
        ],
        "proxima_jornada": {
            "numero": jornada + 1,
            "partidos": [_partido(p) for p in siguiente],
        }
        if siguiente
        else None,
    }

    anterior = ruta_jornada(comp, grupo, jornada - 1)
    lider_anterior = None
    if anterior.exists():
        clas_ant = json.loads(anterior.read_text(encoding="utf-8")).get("clasificacion") or []
        lider_anterior = clas_ant[0]["equipo"] if clas_ant else None
    datos["rankings"] = R.calcular([asdict(ln) for ln in lineas], resumen, datos["clasificacion"])
    datos["datos_jornada"] = D.calcular(
        datos["partidos_temporada"], jornada, datos["candidatos_xv"] + [
            asdict(ln) for ln in lineas if not 1 <= ln.dorsal <= 15],
        actas_jornada, resumen, datos["clasificacion"], lider_anterior,
        [asdict(j) for j in competicion.jugadores],
    )

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
