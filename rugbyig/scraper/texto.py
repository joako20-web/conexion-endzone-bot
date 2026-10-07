"""Normalización del texto de iSquad.

Las páginas son UTF-8 pero traen bytes sueltos en latin-1 ("BAR\\xc7A") y nombres
doblemente codificados ("MARÃ\\x87AL" en vez de "MARÇAL").
"""
import codecs
import re


def _latin1_fallback(err: UnicodeDecodeError):
    return err.object[err.start : err.end].decode("latin-1"), err.end


codecs.register_error("latin1_fallback", _latin1_fallback)


def decodificar(raw: bytes) -> str:
    return raw.decode("utf-8", errors="latin1_fallback")


_MOJIBAKE = re.compile(r"[ÃÂ][\x80-\xbf]")


def limpiar(s: str) -> str:
    if _MOJIBAKE.search(s):
        try:
            s = s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return re.sub(r"\s+", " ", s).strip()
