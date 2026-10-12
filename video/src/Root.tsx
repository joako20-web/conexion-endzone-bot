import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { PROPS_BASE } from "./base/tipos";
import { ReelClasificacion, duracionClasificacion } from "./plantillas/clasificacion/ReelClasificacion";
import type { PropsClasificacion } from "./plantillas/clasificacion/tipos";
import { DURACION_REEL_DATO, ReelDato } from "./plantillas/dato/ReelDato";
import type { PropsDato } from "./plantillas/dato/tipos";
import { ReelJornada, duracionReel } from "./plantillas/jornada/ReelJornada";
import type { PropsJornada } from "./plantillas/jornada/tipos";
import { ReelRankings, duracionRankings } from "./plantillas/rankings/ReelRankings";
import type { PropsRankings } from "./plantillas/rankings/tipos";

// Una composición por plantilla. Las props reales las genera Python (rugbyig/videos/)
// y se pasan con --props; aquí solo hay valores vacíos para que el Studio abra.
const metaJornada: CalculateMetadataFunction<PropsJornada> = ({ props }) => ({
  durationInFrames: duracionReel(props.partidos.length || 5),
});
const metaClasificacion: CalculateMetadataFunction<PropsClasificacion> = ({ props }) => ({
  durationInFrames: duracionClasificacion(props.filas.length || 10, props.leyenda.length),
});
const metaRankings: CalculateMetadataFunction<PropsRankings> = ({ props }) => ({
  durationInFrames: duracionRankings(props.bloques.length || 1),
});

const DATO_VACIO: PropsDato = {
  ...PROPS_BASE,
  dato: { numero: "", antes: "", valor: null, despues: "", unidad: "", titular: "", contexto: "", equipo: "", escudo: "" },
  total: 0,
};

const REEL = { fps: 30, width: 1080, height: 1920 } as const;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ReelJornada"
        component={ReelJornada}
        durationInFrames={600}
        {...REEL}
        calculateMetadata={metaJornada}
        defaultProps={{ ...PROPS_BASE, gancho: null, partidos: [], mvp: null, top: [], trasJornada: 1, zonaTop: "" }}
      />
      <Composition
        id="ReelClasificacion"
        component={ReelClasificacion}
        durationInFrames={450}
        {...REEL}
        calculateMetadata={metaClasificacion}
        defaultProps={{ ...PROPS_BASE, filas: [], leyenda: [], trasJornada: 1, ventaja: 0 }}
      />
      <Composition
        id="ReelRankings"
        component={ReelRankings}
        durationInFrames={450}
        {...REEL}
        calculateMetadata={metaRankings}
        defaultProps={{ ...PROPS_BASE, bloques: [], trasJornada: 1 }}
      />
      <Composition
        id="ReelDato"
        component={ReelDato}
        durationInFrames={DURACION_REEL_DATO}
        {...REEL}
        defaultProps={DATO_VACIO}
      />
    </>
  );
};
