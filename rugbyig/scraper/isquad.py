"""Cliente HTTP de resultadosrugby.isquad.es con caché en disco y pausas."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from rugbyig.models import Acta, Competicion, FilaClasificacion
from rugbyig.scraper import parsers

BASE = "https://resultadosrugby.isquad.es"
PAUSA_S = 0.25
TTL_PAGINAS_S = 120  # las páginas que cambian se reutilizan 2 minutos


class ISquad:
    def __init__(self, cache_dir: Path | str = ".cache/isquad", usar_cache: bool = True):
        self.cache_dir = Path(cache_dir)
        self.usar_cache = usar_cache
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "rugby-ig/0.1 (estadisticas rugby espanol)"
        self._ultima = 0.0
        self._memoria: dict[str, tuple[float, bytes]] = {}

    def _get(self, path: str, params: dict, cachear: bool) -> bytes:
        url = path if path.startswith("http") else f"{BASE}/{path}"
        clave = hashlib.sha1(f"{url}?{sorted(params.items())}".encode()).hexdigest()
        fichero = self.cache_dir / f"{clave}.html"
        if cachear and self.usar_cache and fichero.exists():
            return fichero.read_bytes()
        if not cachear and clave in self._memoria and time.monotonic() - self._memoria[clave][0] < TTL_PAGINAS_S:
            return self._memoria[clave][1]
        espera = PAUSA_S - (time.monotonic() - self._ultima)
        if espera > 0:
            time.sleep(espera)
        for intento in range(3):
            try:
                r = self.sesion.get(url, params=params, timeout=30)
                r.raise_for_status()
                break
            except requests.RequestException:
                if intento == 2:
                    raise
                time.sleep(5 * (intento + 1))
        self._ultima = time.monotonic()
        if cachear:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            fichero.write_bytes(r.content)
        else:
            self._memoria[clave] = (time.monotonic(), r.content)
        return r.content

    @staticmethod
    def _params(id_grupo: int) -> dict:
        return {
            "seleccion": 0,
            "id": id_grupo,
            "id_ambito": 0,
            "id_territorial": 9999,
            "id_superficie": 1,
        }

    # Las páginas que cambian durante la temporada no se cachean.
    def competicion(self, id_grupo: int) -> Competicion:
        raw = self._get("mostrar_estadisticas.php", self._params(id_grupo), cachear=False)
        return parsers.estadisticas(raw)

    def clasificacion(self, id_grupo: int) -> list[FilaClasificacion]:
        raw = self._get("clasificacion.php", self._params(id_grupo), cachear=False)
        return parsers.clasificacion(raw)

    def _opciones(self, params: dict, select: str) -> list[tuple[int, str]]:
        import re

        raw = self._get("competicion.php", params, cachear=False).decode("utf-8", "replace")
        m = re.search(rf"<select id='{select}'.*?</select>", raw, re.S)
        if not m:
            return []
        return [(int(v), " ".join(n.split())) for v, n in re.findall(r"<option[^>]*value='(\d+)'[^>]*>([^<]*)", m.group(0))]

    def descubrir(self, id_temp: int) -> list[dict]:
        """Federaciones, competiciones y grupos publicados en iSquad para una temporada."""
        base = {"seleccion": 0, "id_ambito": 0, "id_temp": id_temp}
        out = []
        for id_terr, terr in self._opciones(base, "territorial"):
            p = {**base, "id_territorial": id_terr}
            for id_comp, comp in self._opciones(p, "competiciones"):
                pc = {**p, "id_competicion": id_comp}
                for id_fase, fase in self._opciones(pc, "fase") or [(0, "")]:
                    pf = {**pc, "id_fase": id_fase} if id_fase else pc
                    for id_grupo, grupo in self._opciones(pf, "grupo"):
                        out.append({"territorial": terr, "competicion": comp, "fase": fase,
                                    "grupo": grupo, "id_grupo": id_grupo})
        return out

    def imagen(self, url: str) -> bytes:
        return self._get(url, {}, cachear=True)

    def acta(self, id_partido: int) -> Acta:
        # Un acta de partido finalizado ya no cambia: se cachea.
        raw = self._get("acta.php", {"id_partido": id_partido}, cachear=True)
        return parsers.acta(raw, id_partido)


_COMPARTIDO: ISquad | None = None


def compartido() -> ISquad:
    """Cliente único del proceso, para aprovechar la caché en memoria entre llamadas."""
    global _COMPARTIDO
    if _COMPARTIDO is None:
        _COMPARTIDO = ISquad()
    return _COMPARTIDO


_MATCHREADY: dict[str, ISquad] = {}


def cliente_para(cfg_comp: dict) -> ISquad:
    """Cliente de la plataforma de esa competición (iSquad por defecto, o MatchReady)."""
    if cfg_comp.get("fuente") == "matchready":
        from rugbyig.scraper.matchready import MatchReady

        base = cfg_comp["base"]
        if base not in _MATCHREADY:
            _MATCHREADY[base] = MatchReady(base)
        return _MATCHREADY[base]
    return compartido()
