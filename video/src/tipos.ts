export type Equipo = {
  nombre: string;
  abr: string;
  escudo: string;
  puntos: number | null;
  gana: boolean;
};

export type Partido = { local: Equipo; visitante: Equipo };

export type Fuente = { familia: string; peso: string; archivo: string; rango: string };

export type PropsReel = {
  competicion: string;
  corto: string;
  jornada: number;
  temporada: string;
  handle: string;
  logo: string;
  tema: Record<string, string>;
  fuenteTitulo: string;
  fuenteTexto: string;
  fuentes: Fuente[];
  gancho: { numero: string; unidad: string; titular: string; escudo: string } | null;
  partidos: Partido[];
  mvp: {
    nombre: string;
    apellidos: string;
    equipo: string;
    escudo: string;
    posicion: string;
    dorsal: number | null;
    puntos: number;
    stats: { valor: number; texto: string }[];
  } | null;
  top: { pos: number; nombre: string; escudo: string; pt: number; pj: number; zona: string }[];
  trasJornada: number;
  zonaTop: string;
};
