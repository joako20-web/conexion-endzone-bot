"""Orquestación del bot de Telegram.

- `semana`: el lunes manda el carrusel de la última jornada de cada liga (el
  martes reintenta los que tenían actas incompletas).
- `procesar`: atiende botones, cambios del XV, fotos de portada y pedidos
  ("xv de dhb", "clasificación élite"...).
- `bucle`: escucha Telegram durante N minutos (lo lanza GitHub Actions).
"""
from __future__ import annotations

import html
import json
import tempfile
import time
import traceback
from pathlib import Path

from rugbyig import caption, directo, estado, torneo
from rugbyig.core.editar import cambiar_xv
from rugbyig.pedidos import interpretar
from rugbyig.pipeline import RAIZ, cargar_config, jornadas_jugadas, preparar_jornada
from rugbyig.render import nombres
from rugbyig.render.render import CLAVES, TEMAS, hoja_muestras, renderizar_jornada, tema_actual
from rugbyig.telegram import Telegram

# Claves de slide abreviadas para caber en los 64 bytes de un botón.
ABREV = {"portada": "p", "resultados": "r", "anotadores": "a", "xv": "x",
         "clasificacion": "c", "previa": "v", "temporada": "t", "datos": "d",
         "grupos": "g", "cuadro": "k",
         "ensayadores": "y", "ensayadores_t": "Y", "pateadores": "f", "pateadores_t": "F",
         "disciplina": "j", "banquillo": "b", "equipos": "q"}
# Imágenes de nivel competición (no dependen de un grupo ni de una jornada).
DE_COMPETICION = {"grupos", "cuadro"}
DESABREV = {v: k for k, v in ABREV.items()}

AYUDA = (
    "<b>Cada lunes</b> te mando el carrusel de cada liga listo para subir, el texto del post "
    "para copiar y las tarjetas de <b>💡 el dato de la jornada</b>.\n"
    "<b>El fin de semana</b>, en cuanto acaba un partido de DH, Élite o Iberdrola, te llega "
    "su <b>🏁 resultado final</b> en formato historia.\n\n"
    "Debajo de cada envío:\n"
    "📱 <b>Historias</b>: lo mismo en vertical 9:16.\n"
    "📦 <b>Original</b>: como archivo, sin la compresión de Telegram.\n"
    "✏️ <b>Cambiar XV</b>: después escribe el dorsal y el nombre, p. ej. <code>9 Araña</code>.\n"
    "📷 <b>Foto portada</b>: después mándame la foto.\n\n"
    "📋 <b>Pedir</b> (botón de abajo o /pedir): eliges liga, qué quieres y jornada.\n"
    "/semana manda ya los carruseles de la semana.\n"
    "/estilo cambia el estilo visual (5 opciones, con muestras)."
)


NOVEDADES = (
    "🆕 <b>Novedades</b>\n"
    "· Menú por niveles: Nacionales · Copa del Rey · Regionales (Castilla y León) y M23.\n"
    "· 🎨 <b>Estilo</b>: 5 estilos visuales con muestras (botón de abajo).\n"
    "· Todo va bastante más rápido."
)


def _rel(p: Path) -> str:
    return str(p.relative_to(RAIZ))


def _titulo(post: dict) -> str:
    cfg = cargar_config()["competiciones"][post["competicion"]]
    grupo = "" if post["grupo"] == "unico" else f" · Grupo {post['grupo']}"
    return f"{cfg['nombre']}{grupo} · Jornada {post['jornada']}"


def _cod(claves: list[str] | None) -> str:
    return "*" if not claves else "".join(ABREV[c] for c in claves)


def _decod(cod: str) -> list[str] | None:
    return None if cod in ("", "*") else [DESABREV[c] for c in cod if c in DESABREV]


def preparar(comp: str, grupo: str, jornada: int | None = None) -> tuple[str, dict]:
    """Descarga datos frescos de la jornada y la registra en el estado."""
    ruta = preparar_jornada(comp, grupo, jornada)
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    pid = estado.id_post(datos["temporada"], comp, grupo, datos["jornada"])
    posts = estado.posts()
    post = posts.get(pid, {})
    post.update(competicion=comp, grupo=grupo, jornada=datos["jornada"], json=_rel(ruta),
                actas_pendientes=datos["actas_pendientes"],
                jugados=sum(p["puntos_local"] is not None for p in datos["partidos"]))
    posts[pid] = post
    estado.guardar_posts(posts)
    return pid, post


def enviar(tg: Telegram, chat_id, pid: str, post: dict, claves: list[str] | None = None,
           nota: str = "", formato: str = "post", original: bool = False) -> None:
    """Genera las imágenes (el carrusel o solo `claves`) y las manda con sus botones.

    formato: "post" (4:5) o "historia" (9:16). original: como archivo, sin compresión.
    """
    datos = json.loads((RAIZ / post["json"]).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        imagenes = renderizar_jornada(RAIZ / post["json"], Path(tmp), claves, formato)
        if not imagenes:
            tg.mensaje(chat_id, f"No hay nada que enseñar de <b>{_titulo(post)}</b> todavía.")
            return
        tg.album(chat_id, imagenes, como_archivo=original)
    if original:
        return  # los originales van sin botones ni textos: ya se mandó la versión normal

    cod, fmt = _cod(claves), formato[0]
    lineas = [f"<b>{_titulo(post)}</b>" + (" · 📱 historias" if formato == "historia" else "")]
    if nota:
        lineas.append(nota)
    if datos["actas_pendientes"] and formato == "post":
        lineas.append(
            f"⚠️ {len(datos['actas_pendientes'])} acta(s) sin completar en la web de la federación: "
            "sus estadísticas aún no cuentan."
        )
    completo = claves is None
    filas = []
    if formato == "post":
        edicion = []
        if datos.get("xv_ideal") and (completo or "xv" in claves):
            edicion.append(("✏️ Cambiar XV", f"xv|{pid}|{cod}"))
        if completo or "portada" in claves:
            edicion.append(("📷 Foto portada", f"foto|{pid}|{cod}"))
        if edicion:
            filas.append(edicion)
        filas.append([("📱 Historias", f"h|{pid}|{cod}"), ("📦 Original", f"o|{pid}|{cod}|p")])
    else:
        filas.append([("📦 Original", f"o|{pid}|{cod}|h")])
    tg.mensaje(chat_id, "\n".join(lineas), filas)
    if completo and formato == "post":
        tg.mensaje(chat_id, "📋 Texto para el post (mantén pulsado para copiar):")
        tg.mensaje(chat_id, html.escape(caption.texto_post(datos)))


def _novedad_competicion(comp: str) -> str | None:
    """Clave que cambia cuando hay algo nuevo a nivel competición (jornada de
    grupos o eliminatoria jugada). None si no hay nada jugado."""
    dc = torneo.datos_competicion(comp)
    j = torneo.ultima_jornada(dc)
    elim = sum(p["puntos_local"] is not None for p in dc["eliminatorias"])
    if not j and not elim:
        return None
    return f"{cargar_config()['temporada'].replace('/', '-')}_{comp}_comp_j{j or 0}_e{elim}"


def _semana_competicion(tg: Telegram, chat_id, comp: str, claves: list[str], nota: str) -> str | None:
    try:
        clave = _novedad_competicion(comp)
    except Exception:
        tg.mensaje(chat_id, f"❗ Error preparando {comp}:\n<code>{html.escape(traceback.format_exc()[-700:])}</code>")
        return None
    posts = estado.posts()
    if not clave or clave in posts:
        return None
    if enviar_competicion(tg, chat_id, comp, claves, nota=nota):
        posts[clave] = {"competicion": comp, "enviado": estado.ahora().isoformat()}
        estado.guardar_posts(posts)
        return clave
    return None


def semana(tg: Telegram, chat_id, reintento: bool = False) -> list[str]:
    hechos = []
    for comp, cfg in cargar_config()["competiciones"].items():
        if cfg.get("semanal", True) is False:
            continue
        if cfg.get("torneo"):
            if not reintento and (h := _semana_competicion(
                    tg, chat_id, comp, ["resultados", "grupos", "cuadro"], "Resumen de la semana")):
                hechos.append(h)
            continue
        enviados_antes = len(hechos)
        for grupo in cfg["grupos"]:
            try:
                pid, post = preparar(comp, grupo)
            except RuntimeError:
                continue  # liga sin jornadas jugadas todavía
            except Exception:
                tg.mensaje(chat_id, f"❗ Error preparando {comp}/{grupo}:\n<code>{html.escape(traceback.format_exc()[-700:])}</code>")
                continue
            if post.get("enviado"):
                # Ya mandada: solo se reenvía en el reintento si se completaron actas.
                if not (reintento and post.get("pendientes_al_enviar") and not post["actas_pendientes"]):
                    continue
                nota = "🔄 Versión actualizada: ya están todas las actas."
            else:
                nota = ""
            enviar(tg, chat_id, pid, post, None, nota)
            if json.loads((RAIZ / post["json"]).read_text(encoding="utf-8")).get("datos_jornada"):
                enviar(tg, chat_id, pid, post, ["datos"], "💡 El dato de la jornada: para post suelto o historias.")
            posts = estado.posts()
            posts[pid]["enviado"] = estado.ahora().isoformat()
            posts[pid]["pendientes_al_enviar"] = bool(post["actas_pendientes"])
            estado.guardar_posts(posts)
            hechos.append(pid)
        if reintento or len(hechos) == enviados_antes:
            continue
        extra = (["grupos"] if len(cfg["grupos"]) > 1 else []) + (["cuadro"] if cfg.get("playoff") else [])
        if extra:
            # El cuadro "si acabara hoy" solo va en los pedidos; aquí solo el real
            dc = torneo.datos_competicion(comp)
            if "cuadro" in extra and not dc["eliminatorias"]:
                extra.remove("cuadro")
            if extra:
                enviar_competicion(tg, chat_id, comp, extra, nota="Visión de toda la competición")
    return hechos


# ---------- Menús con botones: liga -> qué -> jornada ----------

TECLADO_FIJO = [["📋 Pedir", "🎨 Estilo", "❓ Ayuda"]]
VERSION_TECLADO = 2  # súbelo al cambiar el teclado fijo para que se reenvíe
COMANDOS = [("pedir", "Pedir resultados, XV, clasificación…"),
            ("estilo", "Cambiar el estilo visual"),
            ("semana", "Mandar ya los carruseles de esta semana"),
            ("ayuda", "Cómo funciona")]
QUE = [("🧾 Carrusel completo", "*"), ("📊 Resultados", "r"), ("📅 Próxima jornada", "v"),
       ("🔢 Clasificación", "c"), ("🗂 Todos los grupos", "g"), ("🏆 Cuadro / play-off", "k"),
       ("⭐ XV ideal", "x"), ("🎯 Anotadores", "a"), ("📈 Anotadores temporada", "t"),
       ("💡 El dato de la jornada", "d"), ("🖼 Portada", "p"),
       ("🏉 Ensayadores (jornada)", "y"), ("🏉 Ensayadores (temporada)", "Y"),
       ("🦶 Puntos al pie (jornada)", "f"), ("🦶 Pateadores (temporada)", "F"),
       ("🟨 Tarjetas", "j"), ("🔄 Desde el banquillo", "b"), ("📊 La liga en números", "q")]
# Submenú "Más estadísticas"
FILAS_STATS = [["t"], ["y", "Y"], ["f", "F"], ["j", "b"], ["q"], ["d"]]
# Imágenes de temporada: no se elige jornada
DE_TEMPORADA = {"t", "Y", "F", "j", "b", "q", "v", "g", "k"}
# Filas del menú "¿qué quieres?" (agrupadas por tema)
FILAS_QUE = [["*"], ["r", "v"], ["c", "g", "k"], ["x", "a"], ["+"], ["p"]]
CATEGORIAS = {"nacional": "🇪🇸 Nacionales", "copa": "🏆 Copa del Rey", "regional": "🗺 Regionales"}


def _filas(botones: list[tuple[str, str]], ancho: int) -> list[list[tuple[str, str]]]:
    return [botones[i : i + ancho] for i in range(0, len(botones), ancho)]


def _comps(categoria: str | None = None, region: str | None = None) -> dict[str, dict]:
    return {k: v for k, v in cargar_config()["competiciones"].items()
            if (categoria is None or v.get("categoria", "nacional") == categoria)
            and (region is None or v.get("region") == region)}


def _regiones() -> list[str]:
    return sorted({v["region"] for v in _comps("regional").values() if v.get("region")})


def _nombre_liga(liga: str) -> str:
    comp, grupo = liga.split("/")
    cfg = cargar_config()["competiciones"][comp]
    if grupo == "*":
        return f"{cfg['nombre']} (todos los grupos)"
    return cfg["nombre"] + ("" if grupo == "unico" else f" · Grupo {grupo}")


def _boton_liga(comp: str, cfg: dict) -> tuple[str, str]:
    if len(cfg["grupos"]) > 1 and not cfg.get("torneo"):
        return (f"{cfg['nombre']} ▸", f"mg|{comp}")
    return (cfg["nombre"], f"m2|{comp}/{'*' if cfg.get('torneo') else next(iter(cfg['grupos']))}")


def _atras_de(comp: str) -> str:
    cfg = cargar_config()["competiciones"][comp]
    if cfg.get("categoria") == "regional" and len(_regiones()) > 1:
        return f"mr|{_regiones().index(cfg['region'])}"
    return f"mc|{cfg.get('categoria', 'nacional')}"


def _menu_inicio() -> tuple[str, list]:
    botones = []
    for cat, etiqueta in CATEGORIAS.items():
        comps = _comps(cat)
        if not comps:
            continue
        if cat == "copa" and len(comps) == 1:  # una sola copa: directo a ella
            botones.append((etiqueta, _boton_liga(*next(iter(comps.items())))[1]))
        else:
            botones.append((etiqueta, f"mc|{cat}"))
    return "📋 <b>¿Qué competición?</b>", _filas(botones, 2)


def _menu_categoria(cat: str) -> tuple[str, list]:
    if cat == "regional" and len(_regiones()) > 1:
        botones = [(r, f"mr|{i}") for i, r in enumerate(_regiones())]
        return "🗺 <b>Regionales</b>\n¿Qué federación?", _filas(botones, 2) + [[("⬅️ Volver", "m1")]]
    botones = [_boton_liga(k, v) for k, v in _comps(cat).items()]
    titulo = CATEGORIAS[cat] + (f" · {_regiones()[0]}" if cat == "regional" and _regiones() else "")
    return f"<b>{titulo}</b>\n¿Qué liga?", _filas(botones, 1) + [[("⬅️ Volver", "m1")]]


def _menu_region(i: int) -> tuple[str, list]:
    region = _regiones()[i]
    botones = [_boton_liga(k, v) for k, v in _comps("regional", region).items()]
    return f"🗺 <b>{region}</b>\n¿Qué liga?", _filas(botones, 1) + [[("⬅️ Volver", "mc|regional")]]


def _menu_grupos(comp: str) -> tuple[str, list]:
    cfg = cargar_config()["competiciones"][comp]
    botones = [(f"Grupo {g}", f"m2|{comp}/{g}") for g in cfg["grupos"]]
    filas = _filas(botones, 4) + [[("Todos los grupos", f"m2|{comp}/*")], [("⬅️ Volver", _atras_de(comp))]]
    return f"<b>{cfg['nombre']}</b>\n¿Qué grupo?", filas


def _menu_que(liga: str) -> tuple[str, list]:
    comp, grupo = liga.split("/")
    cfg = cargar_config()["competiciones"][comp]
    ocultar = set()
    if len(cfg["grupos"]) < 2:
        ocultar.add("g")
    if not torneo.tiene_cuadro(comp):
        ocultar.add("k")
    if not cfg.get("xv_ideal"):
        ocultar.add("x")
    etiqueta = {c: t for t, c in QUE}
    filas = []
    for fila in FILAS_QUE:
        if fila == ["+"]:
            filas.append([("📈 Más estadísticas ▸", f"ms|{liga}")])
            continue
        botones = [(etiqueta[c], f"m3|{liga}|{c}") for c in fila if c not in ocultar]
        if botones:
            filas.append(botones)
    if cfg.get("torneo"):  # Copa: acceso a cada grupo
        filas.append([(f"Grupo {g}", f"m2|{comp}/{g}") for g in cfg["grupos"]][:6])
    atras = f"mg|{comp}" if len(cfg["grupos"]) > 1 and not cfg.get("torneo") else _atras_de(comp)
    if cfg.get("torneo") and grupo != "*":
        atras = f"m2|{comp}/*"
    filas.append([("⬅️ Volver", atras)])
    return f"<b>{_nombre_liga(liga)}</b>\n¿Qué quieres?", filas


def _menu_stats(liga: str) -> tuple[str, list]:
    etiqueta = {c: t for t, c in QUE}
    filas = [[(etiqueta[c], f"m3|{liga}|{c}") for c in fila] for fila in FILAS_STATS]
    return f"<b>{_nombre_liga(liga)}</b>\n📈 Más estadísticas", filas + [[("⬅️ Volver", f"m2|{liga}")]]


def _menu_jornada(liga: str, cod: str) -> tuple[str, list] | None:
    comp, grupo = liga.split("/")
    grupo_ref = next(iter(cargar_config()["competiciones"][comp]["grupos"])) if grupo == "*" else grupo
    if cod in DE_TEMPORADA:
        return None  # siempre lo último
    jugadas = jornadas_jugadas(comp, grupo_ref)
    if len(jugadas) <= 1:
        return None  # nada que elegir: la última
    ultimas = jugadas[-8:]
    botones = [(f"Última (J{ultimas[-1]})", f"m4|{liga}|{cod}|0")]
    botones += [(f"J{j}", f"m4|{liga}|{cod}|{j}") for j in reversed(ultimas[:-1])]
    return f"<b>{_nombre_liga(liga)}</b>\n¿Qué jornada?", _filas(botones, 4) + [[("⬅️ Volver", f"m2|{liga}")]]


def _menu(tg: Telegram, chat_id, cq: dict, partes: list[str]) -> None:
    paso, mid = partes[0], cq["message"]["message_id"]
    if paso == "m1":
        tg.editar(chat_id, mid, *_menu_inicio())
    elif paso == "mc":
        tg.editar(chat_id, mid, *_menu_categoria(partes[1]))
    elif paso == "mr":
        tg.editar(chat_id, mid, *_menu_region(int(partes[1])))
    elif paso == "mg":
        tg.editar(chat_id, mid, *_menu_grupos(partes[1]))
    elif paso == "m2":
        tg.editar(chat_id, mid, *_menu_que(partes[1]))
    elif paso == "ms":
        tg.editar(chat_id, mid, *_menu_stats(partes[1]))
    elif paso in ("m3", "m4"):
        liga, cod = partes[1], partes[2]
        if paso == "m3" and (menu := _menu_jornada(liga, cod)):
            tg.editar(chat_id, mid, *menu)
            return
        jornada = int(partes[3]) if paso == "m4" and partes[3] != "0" else None
        que = dict((c, t) for t, c in QUE)[cod]
        tg.editar(chat_id, mid, f"⏳ {que} · {_nombre_liga(liga)}" + (f" · J{jornada}" if jornada else ""))
        comp, grupo = liga.split("/")
        grupos = list(cargar_config()["competiciones"][comp]["grupos"]) if grupo == "*" else [grupo]
        _servir(tg, chat_id, [(comp, g) for g in grupos], _decod(cod), jornada)
        tg.mensaje(chat_id, "¿Algo más?", [[("🔁 Otra cosa de esta liga", f"m0|{liga}"), ("📋 Otra competición", "m0")]])


def enviar_competicion(tg: Telegram, chat_id, comp: str, claves: list[str],
                       formato: str = "post", original: bool = False, nota: str = "") -> bool:
    """Imágenes de toda la competición (todos los grupos, cuadro, resultados de todos los grupos)."""
    with tempfile.TemporaryDirectory() as tmp:
        imagenes = torneo.renderizar(comp, claves, Path(tmp), formato)
        if not imagenes:
            return False
        tg.album(chat_id, imagenes, como_archivo=original)
    if original:
        return True
    cod = _cod(claves)
    nombre = cargar_config()["competiciones"][comp]["nombre"]
    botones = [[("📦 Original", f"to|{comp}|{cod}|{formato[0]}")]]
    if formato == "post":
        botones[0].insert(0, ("📱 Historias", f"th|{comp}|{cod}"))
    tg.mensaje(chat_id, f"<b>{nombre}</b>" + (f"\n{nota}" if nota else ""), botones)
    return True


def _servir(tg: Telegram, chat_id, ligas: list[tuple[str, str]], claves: list[str] | None, jornada: int | None) -> None:
    de_comp = [c for c in (claves or []) if c in DE_COMPETICION]
    if de_comp:
        for comp in dict.fromkeys(c for c, _ in ligas):
            if not enviar_competicion(tg, chat_id, comp, de_comp):
                tg.mensaje(chat_id, "No hay nada que enseñar todavía (sin grupos o sin play-off).")
        claves = [c for c in claves if c not in DE_COMPETICION]
        if not claves:
            return
    # Torneo (Copa) pedido completo para todos los grupos: un único resumen
    comps = {c for c, _ in ligas}
    if claves is None and len(ligas) > 1 and len(comps) == 1 and \
            cargar_config()["competiciones"][next(iter(comps))].get("torneo"):
        enviar_competicion(tg, chat_id, next(iter(comps)), ["resultados", "grupos", "cuadro"])
        return
    for comp, grupo in ligas:
        try:
            pid, post = preparar(comp, grupo, jornada)
        except RuntimeError:
            nombre = cargar_config()["competiciones"][comp]["nombre"]
            tg.mensaje(chat_id, f"La {nombre} todavía no ha jugado ninguna jornada.")
            continue
        if jornada and not post["jugados"] and claves != ["previa"]:
            tg.mensaje(chat_id, f"<b>{_titulo(post)}</b>: esa jornada aún no se ha jugado.")
            continue
        enviar(tg, chat_id, pid, post, claves)


# ---------- Estilo visual ----------

def _menu_estilo(tg: Telegram, chat_id) -> None:
    actual = tema_actual()
    botones = [(("✅ " if k == actual else "") + v, f"es|{k}") for k, v in TEMAS.items()]
    tg.mensaje(chat_id, "🎨 <b>Estilo de las imágenes</b>\nElige uno o mira antes las muestras.",
               _filas(botones, 3) + [[("👀 Ver muestras de todos", "es|ver")]])


def _estilo(tg: Telegram, chat_id, b: dict, eleccion: str) -> None:
    if eleccion == "ver":
        tg.mensaje(chat_id, "⏳ Preparando muestras de los 5 estilos (tarda un minuto)…")
        posts = estado.posts()
        post = next((p for p in posts.values() if p.get("json") and p.get("competicion") == "dh_masc"), None)
        if not post:
            _, post = preparar("dh_masc", "unico")
        datos = json.loads((RAIZ / post["json"]).read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            for k, nombre in TEMAS.items():
                tg.foto(chat_id, hoja_muestras(datos, k, Path(tmp)), nombre)
        _menu_estilo(tg, chat_id)
        return
    if eleccion in TEMAS:
        b["tema"] = eleccion
        estado.guardar_bot(b)
        tg.mensaje(chat_id, f"🎨 Estilo cambiado a <b>{TEMAS[eleccion]}</b>. Todo lo que te mande a partir de ahora saldrá así.")


def _atender_pedido(tg: Telegram, chat_id, texto: str) -> bool:
    pedido = interpretar(texto)
    if pedido is None:
        return False
    etiquetas = {DESABREV[c]: t.split(" ", 1)[1].lower() for t, c in QUE if c != "*"}
    que = "el carrusel completo" if pedido.claves is None else ", ".join(etiquetas[c] for c in pedido.claves)
    tg.mensaje(chat_id, f"⏳ Preparando {que}…")
    _servir(tg, chat_id, pedido.ligas, pedido.claves, pedido.jornada)
    return True


def procesar(tg: Telegram, actualizaciones: list[dict]) -> None:
    b = estado.bot()
    posts = estado.posts()
    for u in actualizaciones:
        b["offset"] = u["update_id"] + 1
        estado.guardar_bot(b)
        msg = u.get("message") or (u.get("callback_query") or {}).get("message") or {}
        chat_id = msg.get("chat", {}).get("id")

        if b.get("chat_id") is None:
            if (u.get("message") or {}).get("text", "").startswith("/start"):
                b["chat_id"] = chat_id
                estado.guardar_bot(b)
                tg.comandos(COMANDOS)
                tg.mensaje(chat_id, "👋 Listo, este chat queda vinculado a Conexión Endzone.\n\n" + AYUDA,
                           teclado_fijo=TECLADO_FIJO)
            continue
        if chat_id != b["chat_id"]:
            continue  # solo atiendo al chat vinculado

        try:
            if "callback_query" in u:
                _boton(tg, b, posts, u["callback_query"])
            else:
                _mensaje(tg, b, posts, u["message"])
        except Exception:
            tg.mensaje(chat_id, f"❗ Algo ha fallado:\n<code>{html.escape(traceback.format_exc()[-700:])}</code>")
        estado.guardar_bot(b)
        posts = estado.posts()


def _boton(tg: Telegram, b: dict, posts: dict, cq: dict) -> None:
    chat_id = b["chat_id"]
    partes = cq.get("data", "").split("|")
    tg.responder_boton(cq["id"])
    if partes[0] == "m0":
        tg.mensaje(chat_id, *(_menu_que(partes[1]) if len(partes) > 1 else _menu_inicio()))
        return
    if partes[0].startswith("m"):
        b["esperando"] = None
        _menu(tg, chat_id, cq, partes)
        return
    if partes[0] == "es":
        _estilo(tg, chat_id, b, partes[1])
        return
    if partes[0] in ("th", "to"):  # historias / original de imágenes de competición
        cod = partes[2]
        formato = "historia" if partes[0] == "th" or (len(partes) > 3 and partes[3] == "h") else "post"
        enviar_competicion(tg, chat_id, partes[1], _decod(cod) or [], formato, original=partes[0] == "to")
        return
    if partes[0] == "fo":  # original de una historia de resultado final
        comp, grupo = partes[1].split("/")
        with tempfile.TemporaryDirectory() as tmp:
            img = directo.historia_final(comp, grupo, int(partes[2]), Path(tmp))
            tg.album(chat_id, [img], como_archivo=True)
        return
    accion, pid, cod = (partes + ["", ""])[:3]
    if accion in ("h", "o") and pid in posts:
        formato = "historia" if accion == "h" or (len(partes) > 3 and partes[3] == "h") else "post"
        enviar(tg, chat_id, pid, posts[pid], _decod(cod), formato=formato, original=accion == "o")
        return
    post = posts.get(pid)
    if not post:
        tg.mensaje(chat_id, "Ese contenido ya no existe.")
        return
    b["esperando"] = {"accion": accion, "post": pid, "claves": cod, "cambios": 0}
    if accion == "xv":
        datos = json.loads((RAIZ / post["json"]).read_text(encoding="utf-8"))
        xv = "\n".join(
            f"{d}. {nombres.jugador(j['nombre'])['completo']} ({nombres.equipo_abr(j['equipo'])})"
            for d, j in sorted(datos["xv_ideal"].items(), key=lambda x: int(x[0]))
        )
        tg.mensaje(
            chat_id,
            f"✏️ XV de <b>{_titulo(post)}</b>:\n\n{html.escape(xv)}\n\n"
            "Escribe el dorsal y el nombre del que quieres poner (p. ej. <code>9 Araña</code>). "
            "Puedes mandar varios cambios. Cuando acabes escribe <code>listo</code>.",
        )
    elif accion == "foto":
        tg.mensaje(chat_id, f"📷 Mándame la foto para la portada de <b>{_titulo(post)}</b>.")


def _mensaje(tg: Telegram, b: dict, posts: dict, m: dict) -> None:
    chat_id = b["chat_id"]
    texto = (m.get("text") or "").strip()
    esperando = b.get("esperando") or {}
    post = posts.get(esperando.get("post", ""))

    if texto.startswith(("/start", "/ayuda", "/help")) or texto == "❓ Ayuda":
        tg.mensaje(chat_id, AYUDA, teclado_fijo=TECLADO_FIJO)
    elif texto.startswith("/estilo") or texto == "🎨 Estilo":
        _menu_estilo(tg, chat_id)
    elif texto.startswith("/pedir") or texto == "📋 Pedir":
        b["esperando"] = None
        tg.mensaje(chat_id, *_menu_inicio())
    elif texto.startswith("/semana"):
        tg.mensaje(chat_id, "⏳ Preparando los carruseles de esta semana…")
        if not semana(tg, chat_id):
            tg.mensaje(chat_id, "No hay jornadas nuevas desde el último envío. Pídeme la que quieras, p. ej. <code>todo dh</code>.")
    elif m.get("photo") and post and esperando.get("accion") == "foto":
        estado.FOTOS.mkdir(parents=True, exist_ok=True)
        destino = estado.FOTOS / f"{esperando['post']}.jpg"
        destino.write_bytes(tg.descargar(m["photo"][-1]["file_id"]))
        ruta_json = RAIZ / post["json"]
        datos = json.loads(ruta_json.read_text(encoding="utf-8"))
        datos["foto_portada"] = {"archivo": _rel(destino)}
        ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        b["esperando"] = None
        tg.mensaje(chat_id, "📷 Foto recibida, regenero…")
        enviar(tg, chat_id, esperando["post"], post, _decod(esperando["claves"]), "🔄 Con tu foto de portada.")
    elif m.get("photo"):
        tg.mensaje(chat_id, "Para poner una foto de portada pulsa antes 📷 en el carrusel que quieras.")
    elif texto and post and esperando.get("accion") == "xv":
        if texto.lower() in ("listo", "ok", "fin", "ya"):
            b["esperando"] = None
            if esperando.get("cambios"):
                enviar(tg, chat_id, esperando["post"], post, _decod(esperando["claves"]), "🔄 XV actualizado.")
            else:
                tg.mensaje(chat_id, "Sin cambios.")
            return
        ruta_json = RAIZ / post["json"]
        datos = json.loads(ruta_json.read_text(encoding="utf-8"))
        try:
            resultado = cambiar_xv(datos, texto)
        except ValueError as e:
            if interpretar(texto):  # parece un pedido: salir del modo edición
                b["esperando"] = None
                _atender_pedido(tg, chat_id, texto)
            else:
                tg.mensaje(chat_id, f"🤔 {html.escape(str(e))}")
            return
        ruta_json.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        esperando["cambios"] = esperando.get("cambios", 0) + 1
        b["esperando"] = esperando
        tg.mensaje(chat_id, f"✔️ {html.escape(resultado)}\n(escribe <code>listo</code> para ver la imagen)")
    elif texto and _atender_pedido(tg, chat_id, texto):
        pass
    else:
        tg.mensaje(chat_id, "No te he entendido 🤔 Usa el menú:")
        tg.mensaje(chat_id, *_menu_inicio())


def _toca(b: dict, clave: str, dia: int, hora: int) -> bool:
    """¿Toca la tarea semanal `clave` (día 0=lunes, desde la hora dada) y no se ha hecho?"""
    ahora = estado.ahora()
    semana_iso = f"{ahora.isocalendar().year}-W{ahora.isocalendar().week}"
    if ahora.weekday() == dia and ahora.hour >= hora and b.get(clave) != semana_iso:
        b[clave] = semana_iso
        estado.guardar_bot(b)
        return True
    return False


def _cada_cuanto_directo() -> int:
    """Segundos entre comprobaciones de resultados: a menudo el finde, poco entre semana."""
    ahora = estado.ahora()
    if ahora.weekday() >= 5 and 11 <= ahora.hour < 23:
        return 4 * 60
    return 30 * 60


def bucle(tg: Telegram, minutos: float) -> None:
    fin = time.monotonic() + minutos * 60
    ultimo_directo = 0.0
    try:
        tg.comandos(COMANDOS)  # por si se han añadido comandos nuevos
    except Exception:
        pass
    b = estado.bot()
    if b.get("chat_id") and b.get("teclado") != VERSION_TECLADO:
        tg.mensaje(b["chat_id"], NOVEDADES, teclado_fijo=TECLADO_FIJO)
        b["teclado"] = VERSION_TECLADO
        estado.guardar_bot(b)
    while (restante := fin - time.monotonic()) > 5:
        b = estado.bot()
        chat_id = b.get("chat_id")
        if chat_id:
            if _toca(b, "semana_lunes", 0, 10):
                semana(tg, chat_id)
            elif _toca(b, "semana_martes", 1, 10):
                semana(tg, chat_id, reintento=True)
            if time.monotonic() - ultimo_directo > _cada_cuanto_directo():
                ultimo_directo = time.monotonic()
                try:
                    directo.comprobar(tg, b)
                except Exception:
                    traceback.print_exc()
                estado.guardar_bot(b)
        espera = int(min(50, max(1, restante - 5)))
        procesar(tg, tg.actualizaciones(b.get("offset", 0), espera))
