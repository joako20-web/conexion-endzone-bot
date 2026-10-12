"""uso:
  python -m rugbyig generar dh_masc [--grupo A] [--jornada 2]   # imágenes en out/
  python -m rugbyig semana [--reintento]                        # carruseles -> Telegram
  python -m rugbyig bot [--minutos 14]                          # escucha Telegram
  python -m rugbyig video dh_masc [--jornada 2]                 # reel con motion graphics (out/*.mp4)
  python -m rugbyig descubrir [--temporada 2627]                # ligas disponibles en iSquad
"""
import argparse
import os
import sys

from rugbyig.pipeline import preparar_jornada
from rugbyig.render.render import renderizar_jornada


def main() -> None:
    ap = argparse.ArgumentParser(prog="rugbyig")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generar", help="descarga datos de una jornada y genera las imágenes")
    g.add_argument("competicion")
    g.add_argument("--grupo", default="unico")
    g.add_argument("--jornada", type=int, help="por defecto, la última jugada")
    g.add_argument("--sin-imagenes", action="store_true")
    s = sub.add_parser("semana", help="manda a Telegram el carrusel de la última jornada de cada liga")
    s.add_argument("--reintento", action="store_true", help="solo reenvía los que tenían actas incompletas")
    d = sub.add_parser("descubrir", help="lista las ligas publicadas en iSquad (para añadirlas a config)")
    d.add_argument("--temporada", type=int, default=2627, help="p. ej. 2627 = 2026/27")
    v = sub.add_parser("video", help="reel de resultados de una jornada (necesita Node y video/)")
    v.add_argument("competicion")
    v.add_argument("--grupo", default="unico")
    v.add_argument("--jornada", type=int, help="por defecto, la última jugada")
    v.add_argument("--tipo", default="jornada", help="plantilla (ver rugbyig/videos/__init__.py)")
    b = sub.add_parser("bot", help="escucha Telegram durante unos minutos")
    b.add_argument("--minutos", type=float, default=14)
    args = ap.parse_args()

    if args.cmd == "generar":
        ruta = preparar_jornada(args.competicion, args.grupo, args.jornada)
        print(f"datos: {ruta}")
        if not args.sin_imagenes:
            for img in renderizar_jornada(ruta):
                print(f"  {img}")
        return

    if args.cmd == "video":
        from rugbyig.videos import reel

        print(reel(args.competicion, args.grupo, args.jornada, tipo=args.tipo))
        return
    if args.cmd == "descubrir":
        from rugbyig.scraper.isquad import compartido

        for x in compartido().descubrir(args.temporada):
            print(f"{x['id_grupo']:>6}  {x['territorial'][:28]:28}  {x['competicion'][:40]:40}  {x['fase']} / {x['grupo']}")
        return

    from rugbyig import estado, flujo
    from rugbyig.telegram import Telegram

    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        sys.exit("Falta la variable TELEGRAM_TOKEN")
    tg = Telegram(token)
    if args.cmd == "semana":
        chat_id = estado.bot().get("chat_id")
        if not chat_id:
            sys.exit("El bot aún no está vinculado: escríbele /start en Telegram")
        print("enviados:", flujo.semana(tg, chat_id, args.reintento))
    elif args.cmd == "bot":
        flujo.bucle(tg, args.minutos)


if __name__ == "__main__":
    main()
