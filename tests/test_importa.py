"""Que todos los módulos se puedan importar (un error de sintaxis tumba el bot)."""
import importlib
import pkgutil

import rugbyig


def test_todos_los_modulos_importan():
    for m in pkgutil.walk_packages(rugbyig.__path__, "rugbyig."):
        importlib.import_module(m.name)
