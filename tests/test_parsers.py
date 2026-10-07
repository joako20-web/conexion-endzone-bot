from collections import Counter
from pathlib import Path

import pytest

from rugbyig.core import estadisticas as E
from rugbyig.scraper import parsers as P
from rugbyig.scraper.texto import decodificar, limpiar

FX = Path(__file__).parent / "fixtures"


def leer(nombre: str) -> bytes:
    return (FX / nombre).read_bytes()


@pytest.fixture(scope="module")
def comp():
    return P.estadisticas(leer("estadisticas.html"))


def actas_jornada(comp, n):
    return [(p, P.acta(leer(f"acta_{p.id}.html"), p.id)) for p in comp.jornada(n)]


def test_estadisticas(comp):
    assert len(comp.partidos) == 90
    assert comp.ultima_jornada_jugada() == 2
    p = comp.partidos[0]
    assert (p.id, p.jornada, p.local, p.puntos_local, p.puntos_visitante) == (
        17643, 1, "VRAC QUESOS ENTREPINARES", 40, 24
    )
    assert all(p.jugado for p in comp.jornada(2))
    assert not any(p.jugado for p in comp.jornada(3))
    assert comp.jugadores[0].nombre == "SANTIAGO IGNACIO MANSILLA"
    assert comp.jugadores[0].puntos == 42


@pytest.mark.parametrize("jornada", [1, 2])
def test_eventos_suman_el_marcador(comp, jornada):
    for p, a in actas_jornada(comp, jornada):
        assert (a.local, a.visitante) == (p.local, p.visitante)
        assert a.marcador_por_eventos() == (p.puntos_local, p.puntos_visitante)
        assert sorted(j.dorsal for j in a.alineacion_local)[:15] == list(range(1, 16))
        assert sum(j.tantos for j in a.alineacion_local) <= p.puntos_local


def test_tantos_por_jugador_cuadran_con_eventos(comp):
    for p, a in actas_jornada(comp, 2):
        lineas = {(ln.equipo, ln.nombre): ln for ln in E.lineas_partido(p, a)}
        for equipo, alineacion in ((a.local, a.alineacion_local), (a.visitante, a.alineacion_visitante)):
            for j in alineacion:
                assert lineas[(equipo, j.nombre)].puntos == j.tantos, j.nombre


def test_mojibake():
    assert limpiar("MARÃ\x87AL  CARRERAS") == "MARÇAL CARRERAS"
    assert decodificar(b"BAR\xc7A RUGBI") == "BARÇA RUGBI"
    assert decodificar("PEQUEÑO".encode()) == "PEQUEÑO"


def test_clasificacion():
    filas = P.clasificacion(leer("clasificacion.html"))
    assert len(filas) == 10
    assert filas[0].equipo == "VRAC QUESOS ENTREPINARES"
    assert (filas[0].posicion, filas[0].pt, filas[0].pj) == (1, 9, 2)
    assert filas[2].equipo == "VULCANIZADOS ALVAREZ EL SALVADOR"


def test_xv_ideal(comp):
    lineas = [ln for p, a in actas_jornada(comp, 2) for ln in E.lineas_partido(p, a)]
    xv = E.xv_ideal(lineas)
    assert sorted(xv) == list(range(1, 16))
    assert max(Counter(ln.equipo for ln in xv.values()).values()) <= 4
    assert len({ln.nombre for ln in xv.values()}) == 15


def test_ids_partidos_jornada():
    assert P.ids_partidos_jornada(leer("jornada_2.html")) == [17648, 17649, 17650, 17651, 17652]
