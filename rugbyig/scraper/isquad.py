"""Cliente HTTP de resultadosrugby.isquad.es con caché en disco y pausas."""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from rugbyig.models import Acta, Competicion, FilaClasificacion
from rugbyig.scraper import parsers

BASE = "https://resultadosrugby.isquad.es"
PAUSA_S = 1.0


class ISquad:
    def __init__(self, cache_dir: Path | str = ".cache/isquad", usar_cache: bool = True):
        self.cache_dir = Path(cache_dir)
        self.usar_cache = usar_cache
        self.sesion = requests.Session()
        self.sesion.headers["User-Agent"] = "rugby-ig/0.1 (estadisticas rugby espanol)"
        self._ultima = 0.0

    def _get(self, path: str, params: dict, cachear: bool) -> bytes:
        url = path if path.startswith("http") else f"{BASE}/{path}"
        clave = hashlib.sha1(f"{url}?{sorted(params.items())}".encode()).hexdigest()
        fichero = self.cache_dir / f"{clave}.html"
        if cachear and self.usar_cache and fichero.exists():
            return fichero.read_bytes()
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

    def imagen(self, url: str) -> bytes:
        return self._get(url, {}, cachear=True)

    def acta(self, id_partido: int) -> Acta:
        # Un acta de partido finalizado ya no cambia: se cachea.
        raw = self._get("acta.php", {"id_partido": id_partido}, cachear=True)
        return parsers.acta(raw, id_partido)
