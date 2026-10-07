"""JSON de jornada -> carrusel JPEG 1080x1350 (Jinja2 + Playwright)."""
from __future__ import annotations

import base64
import io
import json
from functools import lru_cache
from datetime import datetime
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from playwright.sync_api import sync_playwright

from rugbyig.core.estadisticas import POSICIONES
from rugbyig.pipeline import CONFIG, RAIZ, cargar_config
from rugbyig.render import nombres
from rugbyig.scraper.isquad import ISquad

TEMPLATES = Path(__file__).parent / "templates"
OUT = RAIZ / "out"

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Filas del XV en el campo, delanteros arriba.
FILAS_XV = [(1, 2, 3), (6, 4, 5, 7), (8, 9, 10), (11, 12, 13, 14), (15,)]


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=True)
    env.filters.update(
        corto=nombres.equipo_corto,
        abr=nombres.equipo_abr,
        jugador=nombres.jugador,
        titulo=nombres.titulo,
        posicion=lambda d: POSICIONES.get(int(d), ""),
    )
    return env


def _rango_fechas(partidos: list[dict]) -> str:
    fechas = sorted(datetime.fromisoformat(p["fecha"]) for p in partidos if p["fecha"])
    if not fechas:
        return ""
    a, b = fechas[0], fechas[-1]
    if a.date() == b.date():
        return f"{a.day} {MESES[a.month - 1]} {a.year}"
    if a.month == b.month:
        return f"{a.day}–{b.day} {MESES[b.month - 1]} {b.year}"
    return f"{a.day} {MESES[a.month - 1]} – {b.day} {MESES[b.month - 1]} {b.year}"


def _n(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _fila_anotador(x: dict, temporada: bool = False) -> dict:
    partes = []
    if x.get("ensayos"):
        partes.append(_n(x["ensayos"], "ensayo", "ensayos"))
    if not temporada:
        if x.get("conversiones"):
            partes.append(_n(x["conversiones"], "transf.", "transf."))
        if x.get("golpes"):
            partes.append(_n(x["golpes"], "golpe", "golpes"))
        if x.get("drops"):
            partes.append(_n(x["drops"], "drop", "drops"))
    else:
        partes.append(_n(x["pj"], "partido", "partidos"))
    return {
        "nombre": x["nombre"],
        "equipo": x["equipo"],
        "valor": x["puntos"],
        "detalle": " · ".join(partes),
        "extra": f"vs {nombres.equipo_corto(x['rival'])}" if x.get("rival") else "",
    }


# Claves de slide, en orden de carrusel. Sirven para pedir slides sueltos.
CLAVES = ["portada", "resultados", "anotadores", "xv", "clasificacion", "previa", "temporada"]


def slides_de_jornada(datos: dict) -> list[dict]:
    """El carrusel semanal de una liga: portada, resultados, anotadores, XV,
    clasificación, previa y anotadores de la temporada."""
    j = datos["jornada"]
    slides: list[dict] = []

    foto = datos.get("foto_portada")
    partes = ["resultados"]
    if datos["anotadores"]:
        partes.append("anotadores")
    if datos.get("xv_ideal"):
        partes.append("XV ideal")
    partes.append("clasificación")
    bajada = ", ".join(partes[:-1]) + f" y {partes[-1]}" if len(partes) > 1 else partes[0]
    destacado = None
    if datos.get("xv_ideal"):
        mvp = max(datos["xv_ideal"].values(), key=lambda x: x["nota"])
        destacado = {"motivo": "Mejor jugador de la jornada", "jugador": mvp["nombre"], "equipo": mvp["equipo"],
                     "dorsal": mvp["dorsal"], "linea": _fila_anotador(mvp)["detalle"], "puntos": mvp["puntos"]}
    elif datos["anotadores"]:
        top = datos["anotadores"][0]
        destacado = {"motivo": "Máximo anotador de la jornada", "jugador": top["nombre"], "equipo": top["equipo"],
                     "dorsal": top["dorsal"], "linea": _fila_anotador(top)["detalle"], "puntos": top["puntos"]}
    slides.append(
        {
            "tipo": "portada",
            "clave": "portada",
            "foto": _foto(foto) if foto else None,
            "bajada": f"{bajada[:1].upper()}{bajada[1:]}",
            "credito": destacado,
        }
    )
    slides.append(
        {"tipo": "resultados", "clave": "resultados", "partidos": datos["partidos"], "fechas": _rango_fechas(datos["partidos"])}
    )
    if datos["anotadores"]:
        slides.append(
            {
                "tipo": "ranking",
                "clave": "anotadores",
                "sup": f"Jornada {j}",
                "titulo": "Máximos anotadores",
                "unidad": "PTS",
                "filas": [_fila_anotador(x) for x in datos["anotadores"][:7]],
            }
        )
    if datos.get("xv_ideal"):
        xv = datos["xv_ideal"]
        mvp = max(xv, key=lambda d: xv[d]["nota"])
        slides.append(
            {"tipo": "xv", "clave": "xv", "xv": xv, "mvp": int(mvp), "filas": [{"dorsales": d} for d in FILAS_XV]}
        )
    n = len(datos["clasificacion"])
    slides.append(
        {
            "tipo": "clasificacion",
            "clave": "clasificacion",
            "filas": datos["clasificacion"],
            "zona_alta": 6 if n >= 10 else 0,
            "zona_baja": 1 if n >= 10 else 0,
        }
    )
    prox = datos.get("proxima_jornada")
    if prox and prox["partidos"]:
        partidos = []
        for p in prox["partidos"]:
            f = datetime.fromisoformat(p["fecha"]) if p["fecha"] else None
            partidos.append(
                {
                    **p,
                    "dia": f"{DIAS[f.weekday()][:3]} {f.day} {MESES[f.month - 1]}" if f else "Por fijar",
                    "hora": f.strftime("%H:%M") if f else "--:--",
                }
            )
        slides.append({"tipo": "previa", "clave": "previa", "numero": prox["numero"], "partidos": partidos})
    if datos["temporada_anotadores"]:
        slides.append(
            {
                "tipo": "ranking",
                "clave": "temporada",
                "sup": f"Temporada {datos['temporada']}",
                "titulo": "Anotadores de la liga",
                "unidad": "PTS",
                "filas": [_fila_anotador(x, True) for x in datos["temporada_anotadores"][:7]],
            }
        )
    return slides


def _data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _foto(foto: dict) -> str:
    """Foto de portada: un archivo local puesto a mano o una URL de iSquad."""
    if foto.get("archivo"):
        ruta = RAIZ / foto["archivo"]
        mime = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
        return _data_uri(ruta.read_bytes(), mime)
    return _data_uri(ISquad().imagen(foto["url"]), "image/jpeg")


@lru_cache(maxsize=512)
def _escudo_uri(url: str) -> str:
    """Escudo reducido a 200 px (los originales son JPEG de 800 px con fondo blanco)."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(ISquad().imagen(url))).convert("RGB")
    except Exception:
        return ""
    img.thumbnail((200, 200))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return _data_uri(buf.getvalue(), "image/jpeg")


def html_post(datos: dict, slides: list[dict]) -> str:
    cfg = cargar_config()["competiciones"][datos["competicion"]]
    marca = yaml.safe_load((CONFIG / "marca.yaml").read_text(encoding="utf-8"))
    logo = _data_uri((RAIZ / marca["logo"]).read_bytes(), "image/png")
    escudos = datos.get("escudos", {})
    env = _env()
    env.filters["escudo"] = lambda equipo: _escudo_uri(escudos[equipo]) if equipo in escudos else ""
    return (
        env
        .get_template("post.html.j2")
        .render(
            slides=slides,
            marca=marca,
            logo=logo,
            jornada=datos["jornada"],
            temporada=datos["temporada"],
            comp={
                "nombre": cfg["nombre"],
                "corto": cfg["corto"],
                "grupo": None if datos["grupo"] == "unico" else f"Grupo {datos['grupo']}",
            },
        )
    )


def renderizar_jornada(
    ruta_json: Path, destino: Path | None = None, claves: list[str] | None = None
) -> list[Path]:
    """Genera el carrusel (o solo los slides de `claves`) como JPEG."""
    datos = json.loads(Path(ruta_json).read_text(encoding="utf-8"))
    destino = destino or OUT / datos["competicion"] / datos["grupo"] / f"j{datos['jornada']:02d}"
    destino.mkdir(parents=True, exist_ok=True)
    for viejo in destino.glob("*.jpg"):
        viejo.unlink()
    slides = slides_de_jornada(datos)
    if claves:
        slides = [s for s in slides if s["clave"] in claves]
    if not slides:
        return []
    generados: list[Path] = []
    with sync_playwright() as pw:
        nav = pw.chromium.launch()
        pagina = nav.new_page(viewport={"width": 1080, "height": 1350})
        pagina.set_content(html_post(datos, slides), wait_until="networkidle")
        pagina.evaluate("document.fonts.ready")
        for sec, s in zip(pagina.query_selector_all("section.slide"), slides):
            jpg = destino / f"{len(generados) + 1:02d}_{s['clave']}.jpg"
            sec.screenshot(path=str(jpg), type="jpeg", quality=92)
            generados.append(jpg)
        nav.close()
    return generados
