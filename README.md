# Conexión Endzone · datos del rugby español

Bot de Telegram que prepara carruseles de Instagram con los datos de las ligas
nacionales de la FER: resultados, máximos anotadores, XV ideal, clasificación,
próxima jornada y anotadores de la temporada. Las imágenes se suben a mano.

- **Datos**: [resultadosrugby.isquad.es](https://resultadosrugby.isquad.es) (la web de resultados de la FER).
- **Sin IA**: todo son cálculos fijos (sumas de las actas y una fórmula para el XV).
- **Gratis**: corre en GitHub Actions; no hace falta tener ningún ordenador encendido.

## Qué hace el bot

- **Lunes 10:00**: manda el carrusel de la última jornada de cada liga, el texto del post para copiar
  y las tarjetas de **💡 el dato de la jornada** (rachas, remontadas, récords, nuevo líder...).
  En la Copa, un resumen único (resultados, fase de grupos y cuadro); en la DH B, además, todos los grupos en una imagen.
- **Martes 10:00**: reenvía los que tenían actas sin completar en la web de la federación.
- **Fin de semana**: en cuanto acaba un partido de DH, Élite, Iberdrola o Copa, manda su **🏁 resultado final** como historia.
- **📋 Pedir** (o `/pedir`): menú con botones *liga → qué → jornada* (incluye todos los grupos y el cuadro / play-off).
- **📱 Historias** y **📦 Original** debajo de cada envío: versión 9:16 y archivos sin comprimir.
- **✏️ Cambiar XV**: escribe `9 Araña` para poner a ese jugador de 9; `listo` para ver la imagen.
- **📷 Foto portada**: manda una foto y la portada pasa a llevarla a sangre.
- `/semana` manda ya los carruseles de la semana.
- Atajo de texto: `xv dhb grupo A`, `clasificación élite`, `cuadro copa`, `resultados dh jornada 1`...

Las clasificaciones llevan una franja de color por zona (título, ascenso, promoción, descenso) con su leyenda,
configurada en `config/competiciones.yaml` según el formato oficial de cada temporada.

## Puesta en marcha (una vez)

1. En Telegram, habla con [@BotFather](https://t.me/BotFather) → `/newbot` → copia el token.
2. Guárdalo como secreto del repo: `gh secret set TELEGRAM_TOKEN` (o en GitHub: *Settings → Secrets and variables → Actions*).
3. En la pestaña *Actions* del repo, lanza el workflow **bot** (*Run workflow*).
4. Escríbele `/start` a tu bot. El primer chat que lo haga queda vinculado y el bot ignora a cualquier otro.

## Mantenimiento

| Qué | Dónde |
|---|---|
| Ids de las ligas, zonas de clasificación, play-off y ligas con resultado en directo | `config/competiciones.yaml` |
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
