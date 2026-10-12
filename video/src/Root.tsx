import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { PROPS_BASE } from "./base/tipos";
import { ReelJornada, duracionReel } from "./plantillas/jornada/ReelJornada";
import type { PropsJornada } from "./plantillas/jornada/tipos";

// Una composición por plantilla. Las props reales las genera Python (rugbyig/videos/)
// y se pasan con --props; aquí solo hay valores vacíos para que el Studio abra.
const metaJornada: CalculateMetadataFunction<PropsJornada> = ({ props }) => ({
  durationInFrames: duracionReel(props.partidos.length || 5),
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
    </>
  );
};
