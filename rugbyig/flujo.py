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

from rugbyig import caption, estado
from rugbyig.core.editar import cambiar_xv
from rugbyig.pedidos import interpretar
from rugbyig.pipeline import RAIZ, cargar_config, jornadas_jugadas, preparar_jornada
from rugbyig.render import nombres
from rugbyig.render.render import CLAVES, renderizar_jornada
from rugbyig.telegram import Telegram

# Claves de slide abreviadas para caber en los 64 bytes de un botón.
ABREV = {"portada": "p", "resultados": "r", "anotadores": "a", "xv": "x",
         "clasificacion": "c", "previa": "v", "temporada": "t"}
DESABREV = {v: k for k, v in ABREV.items()}

AYUDA = (
    "Cada lunes te mando el carrusel de cada liga listo para subir, con el texto "
    "del post aparte para copiarlo.\n\n"
    "✏️ <b>Cambiar XV</b>: después escribe el dorsal y el nombre, p. ej. <code>9 Araña</code>.\n"
    "📷 <b>Foto portada</b>: después mándame la foto.\n\n"
    "📋 <b>Pedir</b> (botón de abajo o /pedir): eliges liga, qué quieres y jornada, y te lo mando.\n"
    "/semana manda ya los carruseles de la semana.\n\n"
    "Atajo: también puedes escribirlo, p. ej. <code>xv dhb grupo A</code> o <code>clasificación élite</code>."
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


def enviar(tg: Telegram, chat_id, pid: str, post: dict, claves: list[str] | None = None, nota: str = "") -> None:
    """Genera las imágenes (todas o solo `claves`) y las manda con sus botones."""
    datos = json.loads((RAIZ / post["json"]).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        imagenes = renderizar_jornada(RAIZ / post["json"], Path(tmp), claves)
        if not imagenes:
            tg.mensaje(chat_id, f"No hay nada que enseñar de <b>{_titulo(post)}</b> todavía.")
            return
        if len(imagenes) == 1:
            tg.foto(chat_id, imagenes[0])
        else:
            tg.album(chat_id, imagenes)

    lineas = [f"<b>{_titulo(post)}</b>"]
    if nota:
        lineas.append(nota)
    if datos["actas_pendientes"]:
        lineas.append(
            f"⚠️ {len(datos['actas_pendientes'])} acta(s) sin completar en la web de la federación: "
            "sus estadísticas aún no cuentan."
        )
    completo = claves is None
    botones = []
    if datos.get("xv_ideal") and (completo or "xv" in claves):
        botones.append(("✏️ Cambiar XV", f"xv|{pid}|{_cod(claves)}"))
    if completo or "portada" in claves:
        botones.append(("📷 Foto portada", f"foto|{pid}|{_cod(claves)}"))
    tg.mensaje(chat_id, "\n".join(lineas), [botones] if botones else None)
    if completo:
        tg.mensaje(chat_id, "📋 Texto para el post (mantén pulsado para copiar):")
        tg.mensaje(chat_id, html.escape(caption.texto_post(datos)))


def semana(tg: Telegram, chat_id, reintento: bool = False) -> list[str]:
    hechos = []
    for comp, cfg in cargar_config()["competiciones"].items():
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
            posts = estado.posts()
            posts[pid]["enviado"] = estado.ahora().isoformat()
            posts[pid]["pendientes_al_enviar"] = bool(post["actas_pendientes"])
            estado.guardar_posts(posts)
            hechos.append(pid)
    return hechos


# ---------- Menús con botones: liga -> qué -> jornada ----------

TECLADO_FIJO = [["📋 Pedir", "❓ Ayuda"]]
QUE = [("🧾 Carrusel completo", "*"), ("📊 Resultados", "r"), ("🎯 Anotadores", "a"),
       ("⭐ XV ideal", "x"), ("🏆 Clasificación", "c"), ("📅 Próxima jornada", "v"),
       ("📈 Anotadores temporada", "t"), ("🖼 Portada", "p")]


def _filas(botones: list[tuple[str, str]], ancho: int) -> list[list[tuple[str, str]]]:
    return [botones[i : i + ancho] for i in range(0, len(botones), ancho)]


def _nombre_liga(liga: str) -> str:
    comp, grupo = liga.split("/")
    cfg = cargar_config()["competiciones"][comp]
    if grupo == "*":
        return f"{cfg['nombre']} (todos los grupos)"
    return cfg["nombre"] + ("" if grupo == "unico" else f" · Grupo {grupo}")


def _menu_ligas() -> tuple[str, list]:
    botones = []
    for comp, cfg in cargar_config()["competiciones"].items():
        grupos = list(cfg["grupos"])
        for g in grupos:
            etiqueta = cfg["corto"] + ("" if g == "unico" else f" {g}")
            botones.append((etiqueta, f"m2|{comp}/{g}"))
        if len(grupos) > 1:
            botones.append((f"{cfg['corto']} (todos)", f"m2|{comp}/*"))
    return "📋 ¿De qué liga?", _filas(botones, 3)


def _menu_que(liga: str) -> tuple[str, list]:
    botones = [(t, f"m3|{liga}|{c}") for t, c in QUE]
    return f"<b>{_nombre_liga(liga)}</b>\n¿Qué quieres?", _filas(botones, 2) + [[("⬅️ Volver", "m1")]]


def _menu_jornada(liga: str, cod: str) -> tuple[str, list] | None:
    comp, grupo = liga.split("/")
    grupo_ref = next(iter(cargar_config()["competiciones"][comp]["grupos"])) if grupo == "*" else grupo
    jugadas = jornadas_jugadas(comp, grupo_ref)
    if cod == "v" or len(jugadas) <= 1:
        return None  # nada que elegir: la última
    ultimas = jugadas[-8:]
    botones = [(f"Última (J{ultimas[-1]})", f"m4|{liga}|{cod}|0")]
    botones += [(f"J{j}", f"m4|{liga}|{cod}|{j}") for j in reversed(ultimas[:-1])]
    return f"<b>{_nombre_liga(liga)}</b>\n¿Qué jornada?", _filas(botones, 4) + [[("⬅️ Volver", f"m2|{liga}")]]


def _menu(tg: Telegram, chat_id, cq: dict, partes: list[str]) -> None:
    paso, mid = partes[0], cq["message"]["message_id"]
    if paso == "m1":
        tg.editar(chat_id, mid, *_menu_ligas())
    elif paso == "m2":
        tg.editar(chat_id, mid, *_menu_que(partes[1]))
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
        tg.mensaje(chat_id, "¿Algo más?", [[("📋 Pedir otra cosa", "m0")]])


def _servir(tg: Telegram, chat_id, ligas: list[tuple[str, str]], claves: list[str] | None, jornada: int | None) -> None:
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
                tg.comandos([("pedir", "Pedir resultados, XV, clasificación…"),
                             ("semana", "Mandar ya los carruseles de esta semana"),
                             ("ayuda", "Cómo funciona")])
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
        tg.mensaje(chat_id, *_menu_ligas())
        return
    if partes[0].startswith("m"):
        b["esperando"] = None
        _menu(tg, chat_id, cq, partes)
        return
    accion, pid, cod = (partes + ["", ""])[:3]
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
    elif texto.startswith("/pedir") or texto == "📋 Pedir":
        b["esperando"] = None
        tg.mensaje(chat_id, *_menu_ligas())
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
        tg.mensaje(chat_id, *_menu_ligas())


def _toca(b: dict, clave: str, dia: int, hora: int) -> bool:
    """¿Toca la tarea semanal `clave` (día 0=lunes, desde la hora dada) y no se ha hecho?"""
    ahora = estado.ahora()
    semana_iso = f"{ahora.isocalendar().year}-W{ahora.isocalendar().week}"
    if ahora.weekday() == dia and ahora.hour >= hora and b.get(clave) != semana_iso:
        b[clave] = semana_iso
        estado.guardar_bot(b)
        return True
    return False


def bucle(tg: Telegram, minutos: float) -> None:
    fin = time.monotonic() + minutos * 60
    while (restante := fin - time.monotonic()) > 5:
        b = estado.bot()
        chat_id = b.get("chat_id")
        if chat_id:
            if _toca(b, "semana_lunes", 0, 10):
                semana(tg, chat_id)
            elif _toca(b, "semana_martes", 1, 10):
                semana(tg, chat_id, reintento=True)
        espera = int(min(50, max(1, restante - 5)))
        procesar(tg, tg.actualizaciones(b.get("offset", 0), espera))
