# Conexión Endzone · datos del rugby español

Bot de Telegram que prepara carruseles de Instagram con los datos de las ligas
nacionales de la FER: resultados, máximos anotadores, XV ideal, clasificación,
próxima jornada y anotadores de la temporada. Las imágenes se suben a mano.

- **Datos**: [resultadosrugby.isquad.es](https://resultadosrugby.isquad.es) (la web de resultados de la FER).
- **Sin IA**: todo son cálculos fijos (sumas de las actas y una fórmula para el XV).
- **Gratis**: corre en GitHub Actions; no hace falta tener ningún ordenador encendido.

## Qué hace el bot

- **Lunes 10:00**: manda el carrusel de la última jornada de cada liga, con el texto del post aparte para copiar.
- **Martes 10:00**: reenvía los que tenían actas sin completar en la web de la federación.
- **📋 Pedir** (o `/pedir`): menú con botones *liga → qué → jornada*.
- **✏️ Cambiar XV**: escribe `9 Araña` para poner a ese jugador de 9; `listo` para ver la imagen.
- **📷 Foto portada**: manda una foto y la portada pasa a llevarla a sangre.
- `/semana` manda ya los carruseles de la semana.
- Atajo de texto: `xv dhb grupo A`, `clasificación élite`, `resultados dh jornada 1`...

## Puesta en marcha (una vez)

1. En Telegram, habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el token.
2. Guárdalo como secreto del repo: `gh secret set TELEGRAM_TOKEN` (o en GitHub: *Settings → Secrets and variables → Actions*).
3. En la pestaña *Actions* del repo, lanza el workflow **bot** (*Run workflow*).
4. Escríbele `/start` a tu bot. El primer chat que lo haga queda vinculado y el bot ignora a cualquier otro.

## Mantenimiento

| Qué | Dónde |
|---|---|
| Ids de las ligas de cada temporada | `config/competiciones.yaml` |
| Nombres cortos y abreviaturas de equipos | `config/equipos.yaml` |
| Cómo mostrar el nombre de un jugador | `config/jugadores.yaml` |
| Hashtags | `config/publicacion.yaml` |
| Logo de la cuenta | `assets/logo_original.png` |
| Fórmula del XV ideal | `rugbyig/core/estadisticas.py` |

## En local

```bash
uv sync
uv run playwright install chromium
uv run python -m rugbyig generar dh_masc          # imágenes en out/
uv run pytest
```
