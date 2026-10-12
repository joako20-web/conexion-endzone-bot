"""Piezas comunes de los vídeos: props de marca/tema/fuentes, escudos y render con Remotion.

Python prepara las props y los efectos de sonido; la animación vive en video/
(una composición por plantilla) y se renderiza con `npx remotion render`.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

import yaml

from rugbyig import sonido
from rugbyig.pipeline import cargar_config, preparar_jornada, ruta_jornada
from rugbyig.render import nombres
from rugbyig.render import render as R
from rugbyig.rutas import CONFIG, RAIZ

VIDEO = RAIZ / "video"
PUBLICO = VIDEO / "public"
TEMAS_CSS = Path(R.__file__).parent / "templates" / "temas.css"
# Familias de cada tema para el vídeo (titulares/números y texto)
FUENTES = {"tele": ("Oswald", "Roboto Condensed")}
_UNO_A_LA_VEZ = threading.Lock()  # el bot puede pedir varios a la vez: se renderizan en fila


def colores_tema(tema: str) -> dict:
    """Variables CSS (--fondo, --acento...) del bloque `.tema-<tema> {` de temas.css."""
    css = TEMAS_CSS.read_text(encoding="utf-8")
    bloque = re.search(r"\.tema-" + tema + r"\s*\{(.*?)\}", css, re.S)
    if not bloque:
        return {}
    return {k: v.strip() for k, v in re.findall(r"--([\w-]+):\s*([^;]+);", bloque.group(1))
            if v.strip().startswith("#")}


def equipo(equipo: str, escudos: dict, puntos: int | None = None, gana: bool = False) -> dict:
    return {"nombre": nombres.equipo_corto(equipo), "abr": nombres.equipo_abr(equipo),
            "escudo": R.escudo_equipo(equipo, escudos), "puntos": puntos, "gana": gana}


def props_base(comp: str, jornada: int, temporada: str, tema: str = "tele") -> dict:
    """Marca, competición, colores del tema y tipografías: lo que llevan todas las plantillas."""
    cfg = cargar_config()["competiciones"][comp]
    marca = yaml.safe_load((CONFIG / "marca.yaml").read_text(encoding="utf-8"))
    tit, txt = FUENTES.get(tema, FUENTES["tele"])
    return {
        "competicion": cfg["nombre"], "corto": cfg.get("corto", cfg["nombre"]), "jornada": jornada,
        "temporada": temporada, "handle": marca["handle"],
        "logo": R._data_uri((RAIZ / marca["logo"]).read_bytes(), "image/png"),
        "tema": colores_tema(tema), "fuenteTitulo": tit, "fuenteTexto": txt,
    }


def datos_jornada(comp: str, grupo: str = "unico", jornada: int | None = None) -> dict:
    """JSON de la jornada. Si ya está guardada se usa tal cual (su clasificación es la de
    aquel momento); si no, se descarga."""
    ruta = ruta_jornada(comp, grupo, jornada) if jornada else None
    if not (ruta and ruta.exists()):
        ruta = preparar_jornada(comp, grupo, jornada)
    return json.loads(ruta.read_text(encoding="utf-8"))


def copiar_fuentes(familias: tuple[str, ...]) -> list[dict]:
    """Copia las woff2 del tema a video/public/fuentes y devuelve su lista para loadFont."""
    origen = RAIZ / "assets" / "fuentes"
    destino = PUBLICO / "fuentes"
    destino.mkdir(parents=True, exist_ok=True)
    lista = []
    for f in json.loads((origen / "fuentes.json").read_text(encoding="utf-8")):
        if f["familia"] in familias:
            shutil.copy2(origen / f["archivo"], destino / f["archivo"])
            lista.append({"familia": f["familia"], "peso": f["peso"], "archivo": f"fuentes/{f['archivo']}",
                          "rango": f["rango"]})
    return lista


def renderizar(composicion: str, props: dict, salida: Path) -> Path:
    """Renderiza una composición de video/ con esas props (añade las fuentes y los sonidos)."""
    salida.parent.mkdir(parents=True, exist_ok=True)
    with _UNO_A_LA_VEZ:
        preparar_node()
        props = {**props, "fuentes": copiar_fuentes((props["fuenteTitulo"], props["fuenteTexto"]))}
        sonido.generar(PUBLICO / "sfx")
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as f:
            json.dump(props, f, ensure_ascii=False)
        try:
            subprocess.run(["npx", "remotion", "render", composicion, str(salida), f"--props={f.name}",
                            "--codec=h264", "--crf=16", "--audio-bitrate=320k", "--log=warn"], cwd=VIDEO, check=True)
        finally:
            Path(f.name).unlink(missing_ok=True)
    return salida


def preparar_node() -> None:
    """Instala las dependencias de video/ la primera vez (en GitHub Actions, en cada ejecución nueva)."""
    if not (VIDEO / "node_modules" / ".bin" / "remotion").exists():
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=VIDEO, check=True)


def foto_jugador(url: str, ancho: int = 720, alto: int = 900) -> str:
    """Foto de iSquad recortada a 4:5 (cara arriba) como data URI, o "" si no hay o es
    pequeña (las de carnet de ~150-500 px se ven pixeladas a ese tamaño)."""
    if not url:
        return ""
    import io

    from PIL import Image

    from rugbyig.pipeline import FOTO_MIN_PX
    from rugbyig.scraper.isquad import compartido

    try:
        img = Image.open(io.BytesIO(compartido().imagen(url))).convert("RGB")
    except Exception:
        return ""
    w, h = img.size
    if min(w, h) < FOTO_MIN_PX:
        return ""
    proporcion = ancho / alto
    if w / h > proporcion:  # más ancha: se recorta por los lados, centrada
        nuevo = round(h * proporcion)
        img = img.crop(((w - nuevo) // 2, 0, (w - nuevo) // 2 + nuevo, h))
    else:  # más alta: se recorta abajo (la cara suele estar en el tercio superior)
        nuevo = round(w / proporcion)
        arriba = round((h - nuevo) * 0.2)
        img = img.crop((0, arriba, w, arriba + nuevo))
    img = img.resize((ancho, alto), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return R._data_uri(buf.getvalue(), "image/jpeg")
