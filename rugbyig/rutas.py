"""Rutas del proyecto (módulo sin dependencias, para evitar importaciones circulares)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config"
DATA = RAIZ / "data"
