import pytest

from rugbyig import pipeline
from rugbyig.rutas import RAIZ

# Copia congelada de data/ (DH masculina, jornadas 1-3): los tests de vídeos y carteles
# no dependen de lo que el bot vaya guardando cada fin de semana.
DATOS_TEST = RAIZ / "tests" / "fixtures" / "data"


@pytest.fixture(autouse=True)
def datos_congelados(monkeypatch):
    monkeypatch.setattr(pipeline, "DATA", DATOS_TEST)
