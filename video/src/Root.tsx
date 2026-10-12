import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { PROPS_BASE } from "./base/tipos";
import { ReelJornada, duracionReel } from "./plantillas/jornada/ReelJornada";
import type { PropsJornada } from "./plantillas/jornada/tipos";
import { ReelPrevia, duracionReel as duracionPrevia } from "./plantillas/previa/ReelPrevia";
import type { PropsPrevia } from "./plantillas/previa/tipos";

// Una composición por plantilla. Las props reales las genera Python (rugbyig/videos/)
// y se pasan con --props; aquí solo hay valores vacíos para que el Studio abra.
const metaJornada: CalculateMetadataFunction<PropsJornada> = ({ props }) => ({
  durationInFrames: duracionReel(props.partidos.length || 5),
});

const metaPrevia: CalculateMetadataFunction<PropsPrevia> = ({ props }) => ({
  durationInFrames: duracionPrevia(props.partidos.length || 5),
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="ReelJornada"
        component={ReelJornada}
        durationInFrames={600}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={metaJornada}
        defaultProps={{ ...PROPS_BASE, gancho: null, partidos: [], mvp: null, top: [], trasJornada: 1, zonaTop: "" }}
      />
      <Composition
        id="ReelPrevia"
        component={ReelPrevia}
        durationInFrames={600}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={metaPrevia}
        defaultProps={{ ...PROPS_BASE, destacado: null, partidos: [], total: 0, equiposTabla: 0 }}
      />
    </>
  );
};
