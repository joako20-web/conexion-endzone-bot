import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { PROPS_BASE } from "./base/tipos";
import { ReelJornada, duracionReel } from "./plantillas/jornada/ReelJornada";
import type { PropsJornada } from "./plantillas/jornada/tipos";
import { ReelMvp, duracionMvp } from "./plantillas/mvp/ReelMvp";
import { ReelXV, duracionXV } from "./plantillas/xv/ReelXV";
import type { PropsXV } from "./plantillas/xv/tipos";

// Una composición por plantilla. Las props reales las genera Python (rugbyig/videos/)
// y se pasan con --props; aquí solo hay valores vacíos para que el Studio abra.
const metaJornada: CalculateMetadataFunction<PropsJornada> = ({ props }) => ({
  durationInFrames: duracionReel(props.partidos.length || 5),
});
const metaXV: CalculateMetadataFunction<PropsXV> = ({ props }) => ({
  durationInFrames: duracionXV(props.lineas.length || 6),
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
        id="ReelXV"
        component={ReelXV}
        durationInFrames={duracionXV(6)}
        fps={30}
        width={1080}
        height={1920}
        calculateMetadata={metaXV}
        defaultProps={{ ...PROPS_BASE, lineas: [], mejor: null }}
      />
      <Composition
        id="ReelMvp"
        component={ReelMvp}
        durationInFrames={duracionMvp()}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{ ...PROPS_BASE, jugador: null }}
      />
    </>
  );
};
