"""Cliente mínimo de la API de bots de Telegram (sondeo con getUpdates)."""
from __future__ import annotations

import json
from contextlib import ExitStack
from pathlib import Path

import requests


class Telegram:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.base_ficheros = f"https://api.telegram.org/file/bot{token}"

    def _post(self, metodo: str, files=None, **datos):
        datos = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in datos.items() if v is not None}
        r = requests.post(f"{self.base}/{metodo}", data=datos, files=files, timeout=120)
        cuerpo = r.json()
        if not cuerpo.get("ok"):
            raise RuntimeError(f"Telegram {metodo}: {cuerpo.get('description')}")
        return cuerpo["result"]

    def actualizaciones(self, offset: int, espera: int = 0) -> list[dict]:
        """getUpdates con sondeo largo: espera hasta `espera` segundos a que llegue algo."""
        datos = {"offset": offset, "timeout": espera,
                 "allowed_updates": json.dumps(["message", "callback_query"])}
        try:
            r = requests.post(f"{self.base}/getUpdates", data=datos, timeout=espera + 30)
            return r.json().get("result", [])
        except requests.RequestException:
            return []

    @staticmethod
    def _teclado(botones):
        if not botones:
            return None
        return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in fila] for fila in botones]}

    def mensaje(self, chat_id, texto: str, botones: list[list[tuple[str, str]]] | None = None,
                teclado_fijo: list[list[str]] | None = None) -> dict:
        teclado = self._teclado(botones)
        if teclado_fijo:
            teclado = {"keyboard": [[{"text": t} for t in fila] for fila in teclado_fijo],
                       "resize_keyboard": True, "is_persistent": True}
        return self._post(
            "sendMessage", chat_id=chat_id, text=texto, parse_mode="HTML",
            reply_markup=teclado, disable_web_page_preview=True,
        )

    def editar(self, chat_id, message_id: int, texto: str, botones=None) -> None:
        try:
            self._post("editMessageText", chat_id=chat_id, message_id=message_id, text=texto,
                       parse_mode="HTML", reply_markup=self._teclado(botones) or {"inline_keyboard": []})
        except RuntimeError:
            pass  # p. ej. "message is not modified"

    def comandos(self, lista: list[tuple[str, str]]) -> None:
        self._post("setMyCommands", commands=[{"command": c, "description": d} for c, d in lista])

    def album(self, chat_id, imagenes: list[Path]) -> None:
        """Envía hasta 10 imágenes como un álbum."""
        for i in range(0, len(imagenes), 10):
            lote = imagenes[i : i + 10]
            with ExitStack() as pila:
                files = {f"f{j}": pila.enter_context(open(p, "rb")) for j, p in enumerate(lote)}
                media = [{"type": "photo", "media": f"attach://f{j}"} for j in range(len(lote))]
                self._post("sendMediaGroup", files=files, chat_id=chat_id, media=media)

    def foto(self, chat_id, imagen: Path, texto: str = "") -> None:
        with open(imagen, "rb") as f:
            self._post("sendPhoto", files={"photo": f}, chat_id=chat_id, caption=texto)

    def responder_boton(self, callback_id: str, texto: str = "") -> None:
        try:
            self._post("answerCallbackQuery", callback_query_id=callback_id, text=texto)
        except RuntimeError:
            pass  # el botón caducó (más de unos minutos): no importa

    def descargar(self, file_id: str) -> bytes:
        info = self._post("getFile", file_id=file_id)
        r = requests.get(f"{self.base_ficheros}/{info['file_path']}", timeout=60)
        r.raise_for_status()
        return r.content
