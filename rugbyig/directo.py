"""Resultado final al momento: vigila las ligas con `directo: true` y, en cuanto
un partido termina, manda una historia 9:16 con el marcador y los anotadores."""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

from rugbyig.core import estadisticas as E
from rugbyig.pipeline import cargar_config
from rugbyig.render import nombres
from rugbyig.render.render import MESES, fila_anotador, renderizar_slides
from rugbyig.scraper.isquad import ISquad, compartido

ESPERA_ACTA_MIN = 40  # si el acta no cuadra, se espera esto antes de mandar solo el marcador
MAX_RECORDADOS = 600


def _ligas() -> list[tuple[str, str, int]]:
    out = []
    for comp, cfg in cargar_config()["competiciones"].items():
        if cfg.get("directo"):
            out += [(comp, g, i) for g, i in cfg["grupos"].items()]
    return out


def historia_final(comp: str, grupo: str, id_partido: int, destino: Path,
                   cliente: ISquad | None = None, forzar: bool = True) -> Path | None:
    """Genera la historia del partido. Con forzar=False devuelve None si el acta
    aún no cuadra con el marcador (para esperar a que se complete)."""
    cliente = cliente or compartido()
    cfg = cargar_config()
    id_grupo = cfg["competiciones"][comp]["grupos"][grupo]
    clasificacion = cliente.clasificacion(id_grupo)
    competicion = cliente.competicion(id_grupo).filtrar(id_grupo, {f.equipo for f in clasificacion})
    p = next(x for x in competicion.partidos if x.id == id_partido)

    anot = {p.local: [], p.visitante: []}
    acta = cliente.acta(p.id)
    completa = acta.marcador_por_eventos() == (p.puntos_local, p.puntos_visitante)
    if not completa and not forzar:
        return None
    if completa:
        for ln in sorted(E.lineas_partido(p, acta), key=lambda x: -x.puntos):
            if ln.puntos:
                fila = fila_anotador({**ln.__dict__, "rival": ""})
                anot[ln.equipo].append({"nombre": ln.nombre, "puntos": ln.puntos, "detalle": fila["detalle"]})

    f = p.fecha
    cuando = f"{cfg['competiciones'][comp]['nombre']} · Jornada {p.jornada}"
    if f:
        cuando += f" · {f.day} {MESES[f.month - 1]}"
    datos = {
        "competicion": comp, "grupo": grupo, "jornada": p.jornada, "temporada": cfg["temporada"],
        "escudos": {x.equipo: x.escudo for x in clasificacion if x.escudo},
    }
    slide = {
        "tipo": "final", "clave": "final", "cuando": cuando,
        "partido": {"local": p.local, "visitante": p.visitante,
                    "puntos_local": p.puntos_local, "puntos_visitante": p.puntos_visitante},
        "anot_local": anot[p.local][:5], "anot_visitante": anot[p.visitante][:5],
        "nota": "" if completa else "Anotadores pendientes del acta oficial",
    }
    return renderizar_slides(datos, [slide], destino, "historia")[0]


def comprobar(tg, b: dict, cliente: ISquad | None = None) -> int:
    """Manda la historia de cada partido terminado que no se haya mandado aún.

    La primera vez solo memoriza los partidos ya jugados (no manda el pasado).
    Devuelve cuántos se han mandado.
    """
    cliente = cliente or compartido()
    primera_vez = "finales" not in b
    enviados = set(b.get("finales", []))
    vistos: dict = b.get("finales_vistos", {})
    ahora = datetime.now().timestamp()
    n = 0
    for comp, grupo, id_grupo in _ligas():
        try:
            clasificacion = cliente.clasificacion(id_grupo)
            competicion = cliente.competicion(id_grupo).filtrar(id_grupo, {f.equipo for f in clasificacion})
        except Exception:
            continue
        for p in competicion.partidos:
            if not p.jugado or p.id in enviados:
                continue
            if primera_vez:
                enviados.add(p.id)
                continue
            visto = vistos.setdefault(str(p.id), ahora)
            forzar = ahora - visto > ESPERA_ACTA_MIN * 60
            with tempfile.TemporaryDirectory() as tmp:
                img = historia_final(comp, grupo, p.id, Path(tmp), cliente, forzar)
                if img is None:
                    continue  # acta aún incompleta: se reintenta en la siguiente vuelta
                tg.foto(b["chat_id"], img)
            tg.mensaje(b["chat_id"], f"🏁 <b>Final</b> · {nombres.equipo_corto(p.local)} {p.puntos_local}-{p.puntos_visitante} {nombres.equipo_corto(p.visitante)}",
                       [[("📦 Original", f"fo|{comp}/{grupo}|{p.id}")]])
            enviados.add(p.id)
            vistos.pop(str(p.id), None)
            n += 1
    b["finales"] = sorted(enviados)[-MAX_RECORDADOS:]
    b["finales_vistos"] = vistos
    return n
