"""JSON de jornada -> carrusel JPEG 1080x1350 (Jinja2 + Playwright).

Claves de slide:
- CLAVES (carrusel por defecto): portada, resultados, anotadores, xv, clasificacion, previa, temporada.
- EXTRA: datos (tarjetas de "el dato de la jornada").
- RANKINGS (solo bajo pedido, no entran en el carrusel):
  · ensayadores    "Máximos ensayadores" de la jornada (ensayos, puntos, rival).
  · pateadores     "Puntos al pie" de la jornada (transformaciones, golpes y drops).
  · ensayadores_t  "Ensayadores de la liga": ensayos en la temporada.
  · pateadores_t   "Pateadores de la liga": puntos al pie en la temporada, con desglose.
  · disciplina     "Tarjetas": jugadores con más amarillas/rojas en la temporada.
  · banquillo      "Desde el banquillo": puntos de suplentes (dorsal 16-23) en la temporada.
  · equipos        "La liga en números": mejor ataque, mejor defensa, más ensayos y más tarjetas.
"""
from __future__ import annotations

import atexit
import base64
import io
import os
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
from rugbyig.scraper.isquad import compartido

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


def fila_anotador(x: dict, temporada: bool = False) -> dict:
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
# Slides que van aparte del carrusel (tarjetas de "el dato de la jornada").
EXTRA = ["datos"]
# Rankings bajo pedido (ver docstring del módulo)
RANKINGS = ["ensayadores", "pateadores", "ensayadores_t", "pateadores_t", "disciplina", "banquillo", "equipos"]
TAMANOS = {"post": (1080, 1350), "historia": (1080, 1920)}


def zonas_de(comp: str, grupo: str) -> list[dict]:
    cfg = cargar_config()["competiciones"][comp]
    return cfg.get("zonas_grupo", {}).get(grupo) or cfg.get("zonas", [])


def con_zonas(clasificacion: list[dict], comp: str, grupo: str) -> tuple[list[dict], list[dict]]:
    """Añade a cada fila su zona (franja de color) y devuelve la leyenda."""
    n = len(clasificacion)
    zonas = []
    for z in zonas_de(comp, grupo):
        desde = z["desde"] if z["desde"] > 0 else n + 1 + z["desde"]
        hasta = z["hasta"] if z["hasta"] > 0 else n + 1 + z["hasta"]
        zonas.append({**z, "desde": desde, "hasta": hasta})
    filas, usadas = [], []
    for f in clasificacion:
        z = next((z for z in zonas if z["desde"] <= f["posicion"] <= z["hasta"]), None)
        filas.append({**f, "zona": z["color"] if z else ""})
        if z and z not in usadas:
            usadas.append(z)
    return filas, [{"color": z["color"], "texto": z["texto"]} for z in usadas]


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
                     "dorsal": mvp["dorsal"], "linea": fila_anotador(mvp)["detalle"], "puntos": mvp["puntos"]}
    elif datos["anotadores"]:
        top = datos["anotadores"][0]
        destacado = {"motivo": "Máximo anotador de la jornada", "jugador": top["nombre"], "equipo": top["equipo"],
                     "dorsal": top["dorsal"], "linea": fila_anotador(top)["detalle"], "puntos": top["puntos"]}
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
                "filas": [fila_anotador(x) for x in datos["anotadores"][:7]],
            }
        )
    if datos.get("xv_ideal"):
        xv = datos["xv_ideal"]
        mvp = max(xv, key=lambda d: xv[d]["nota"])
        slides.append(
            {"tipo": "xv", "clave": "xv", "xv": xv, "mvp": int(mvp), "filas": [{"dorsales": d} for d in FILAS_XV]}
        )
    filas, leyenda = con_zonas(datos["clasificacion"], datos["competicion"], datos["grupo"])
    slides.append({"tipo": "clasificacion", "clave": "clasificacion", "filas": filas, "leyenda": leyenda})
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
                "filas": [fila_anotador(x, True) for x in datos["temporada_anotadores"][:7]],
            }
        )
    slides += [dict(t) for t in datos.get("datos_jornada", [])]
    slides += slides_rankings(datos)
    return slides


def slides_rankings(datos: dict) -> list[dict]:
    """Slides de RANKINGS; se omiten los que no tienen datos."""
    r = datos.get("rankings") or {}
    j, temp = datos["jornada"], f"Temporada {datos['temporada']}"
    defs = [
        ("ensayadores", "Máximos ensayadores", f"Jornada {j}", "ENS"),
        ("pateadores", "Puntos al pie", f"Jornada {j}", "PTS"),
        ("ensayadores_t", "Ensayadores de la liga", temp, "ENS"),
        ("pateadores_t", "Pateadores de la liga", temp, "PTS"),
        ("disciplina", "Tarjetas", temp, "TARJ"),
        ("banquillo", "Desde el banquillo", f"Puntos de suplentes · {temp}", "PTS"),
    ]
    slides = []
    for clave, titulo, sup, unidad in defs:
        filas = r.get(clave) or []
        if not filas:
            continue
        filas = [{**f, "extra": f"vs {nombres.equipo_corto(f['rival'])}" if f.get("rival") else ""} for f in filas]
        slides.append({"tipo": "ranking", "clave": clave, "titulo": titulo, "sup": sup, "unidad": unidad,
                       "filas": filas})
    if r.get("equipos"):
        slides.append({"tipo": "bloques", "clave": "equipos", "titulo": "La liga en números",
                       "sup": f"Tras la jornada {j}", "bloques": r["equipos"]})
    return slides


def _data_uri(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def _foto(foto: dict) -> str:
    """Foto de portada: un archivo local puesto a mano o una URL de iSquad."""
    if foto.get("archivo"):
        ruta = RAIZ / foto["archivo"]
        mime = "image/png" if ruta.suffix.lower() == ".png" else "image/jpeg"
        return _data_uri(ruta.read_bytes(), mime)
    return _data_uri(compartido().imagen(foto["url"]), "image/jpeg")


@lru_cache(maxsize=512)
def _escudo_uri(url: str) -> str:
    """Escudo reducido a 200 px (los originales son JPEG de 800 px con fondo blanco)."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(compartido().imagen(url))).convert("RGB")
    except Exception:
        return ""
    img.thumbnail((200, 200))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return _data_uri(buf.getvalue(), "image/jpeg")


TEMAS = {"noche": "Noche", "tiza": "Tiza", "estadio": "Estadio", "prensa": "Prensa", "cesped": "Césped"}
# Tipografía de titulares de cada tema (el texto siempre va en Barlow Condensed)
FUENTE_TEMA = {"noche": "Teko", "tiza": "Teko", "estadio": "Bebas Neue", "prensa": "Oswald", "cesped": "Anton"}
FUENTES = RAIZ / "assets" / "fuentes"


@lru_cache(maxsize=8)
def css_fuentes(tema: str) -> str:
    """@font-face con las fuentes del tema incrustadas (sin pedir nada a Google)."""
    familias = {"Barlow Condensed", FUENTE_TEMA.get(tema, "Teko"), "Teko"}
    reglas = []
    for f in json.loads((FUENTES / "fuentes.json").read_text()):
        if f["familia"] not in familias:
            continue
        datos = base64.b64encode((FUENTES / f["archivo"]).read_bytes()).decode()
        reglas.append(
            f"@font-face {{ font-family: '{f['familia']}'; font-weight: {f['peso']}; font-style: normal;"
            f" font-display: block; src: url(data:font/woff2;base64,{datos}) format('woff2');"
            f" unicode-range: {f['rango']}; }}"
        )
    return "\n".join(reglas)


def tema_actual() -> str:
    """Tema elegido en Telegram (/estilo) o el de config/marca.yaml."""
    from rugbyig import estado

    marca = yaml.safe_load((CONFIG / "marca.yaml").read_text(encoding="utf-8"))
    tema = estado.bot().get("tema") or marca.get("tema", "noche")
    return tema if tema in TEMAS else "noche"


def html_post(datos: dict, slides: list[dict], formato: str = "post", tema: str | None = None) -> str:
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
            formato=formato,
            tema=(tema := tema or tema_actual()),
            fuentes=css_fuentes(tema),
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


class _Navegador:
    """Un único Chromium para todo el proceso (arrancarlo cuesta ~1 s)."""

    def __init__(self):
        self.pw = self.nav = None

    def pagina(self, ancho: int, alto: int):
        if self.nav is None or not self.nav.is_connected():
            self.pw = sync_playwright().start()
            canal = os.environ.get("PLAYWRIGHT_CHANNEL")  # "chrome" en GitHub: ya viene instalado
            self.nav = self.pw.chromium.launch(channel=canal) if canal else self.pw.chromium.launch()
        pagina = self.nav.new_page(viewport={"width": ancho, "height": alto})
        return pagina

    def cerrar(self):
        if self.nav:
            self.nav.close()
            self.pw.stop()
            self.nav = self.pw = None


_NAV = _Navegador()
atexit.register(_NAV.cerrar)


def renderizar_slides(
    datos: dict, slides: list[dict], destino: Path, formato: str = "post", tema: str | None = None
) -> list[Path]:
    """Pinta los slides dados como JPEG (1080x1350 o 1080x1920)."""
    destino.mkdir(parents=True, exist_ok=True)
    for viejo in destino.glob("*.jpg"):
        viejo.unlink()
    if not slides:
        return []
    ancho, alto = TAMANOS[formato]
    generados: list[Path] = []
    pagina = _NAV.pagina(ancho, alto)
    try:
        pagina.set_content(html_post(datos, slides, formato, tema), wait_until="load")
        pagina.evaluate("document.fonts.ready")
        for sec, s in zip(pagina.query_selector_all("section.slide"), slides):
            jpg = destino / f"{len(generados) + 1:02d}_{s['clave']}.jpg"
            sec.screenshot(path=str(jpg), type="jpeg", quality=92)
            generados.append(jpg)
    finally:
        pagina.close()
    return generados


def renderizar_jornada(
    ruta_json: Path, destino: Path | None = None, claves: list[str] | None = None,
    formato: str = "post",
) -> list[Path]:
    """Genera el carrusel (o solo los slides de `claves`) como JPEG.

    Sin `claves` se genera el carrusel; las tarjetas de datos solo si se piden.
    """
    datos = json.loads(Path(ruta_json).read_text(encoding="utf-8"))
    destino = destino or OUT / datos["competicion"] / datos["grupo"] / f"j{datos['jornada']:02d}"
    slides = slides_de_jornada(datos)
    slides = [s for s in slides if s["clave"] in claves] if claves else [s for s in slides if s["clave"] in CLAVES]
    return renderizar_slides(datos, slides, destino, formato)


def hoja_muestras(datos: dict, tema: str, destino: Path) -> Path:
    """Una imagen con 4 slides de ejemplo en ese tema, para elegir estilo."""
    from PIL import Image

    slides = {s["clave"]: s for s in slides_de_jornada(datos)}
    elegidos = [slides[c] for c in ("portada", "resultados", "clasificacion", "xv") if c in slides]
    imgs = renderizar_slides(datos, elegidos, destino / tema, "post", tema)
    hoja = Image.new("RGB", (2 * 540 + 20, 2 * 675 + 20), (40, 40, 40))
    for i, img in enumerate(imgs[:4]):
        hoja.paste(Image.open(img).resize((540, 675)), ((i % 2) * 560, (i // 2) * 695))
    salida = destino / f"{tema}.jpg"
    hoja.save(salida, quality=88)
    return salida
