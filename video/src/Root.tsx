import React from "react";
import { CalculateMetadataFunction, Composition } from "remotion";
import { ReelJornada, duracionReel } from "./ReelJornada";
import type { PropsReel } from "./tipos";

// Las props reales las genera Python (rugbyig/video.py) y se pasan con --props=public/props.json.
const calcular: CalculateMetadataFunction<PropsReel> = ({ props }) => ({
  durationInFrames: duracionReel(props.partidos.length || 5),
});

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="ReelJornada"
      component={ReelJornada}
      durationInFrames={600}
      fps={30}
      width={1080}
      height={1920}
      calculateMetadata={calcular}
      defaultProps={{
        competicion: "División de Honor",
        corto: "DH",
        jornada: 1,
        temporada: "2026/27",
        handle: "@conexionendzone",
        logo: "",
        tema: {},
        fuenteTitulo: "Oswald",
        fuenteTexto: "Roboto Condensed",
        fuentes: [],
        gancho: null,
        partidos: [],
        mvp: null,
        top: [],
        trasJornada: 1,
        zonaTop: "",
      }}
    />
  );
};
