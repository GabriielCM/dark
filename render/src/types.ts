/**
 * Contrato de props com o Python.
 *
 * Espelha `src/mundoantigo/render/props.py`. As duas definicoes vivem lado a
 * lado de proposito e ha um teste que compara os campos — sem isso, a fronteira
 * entre os dois processos diverge em silencio (ADR 0001).
 */

export type CameraMove =
  | "zoom_in"
  | "zoom_out"
  | "pan_left"
  | "pan_right"
  | "estatica";

export type CharacterSide = "esquerda" | "direita" | "centro";

export type CharacterProps = {
  pose: string;
  svg: string | null;
  position: CharacterSide;
};

export type SubtitleCue = {
  start: number;
  end: number;
  text: string;
};

export type SceneProps = {
  index: number;
  background: string;
  start: number;
  duration: number;
  camera: CameraMove;
  character: CharacterProps | null;
  layers: string[];
  music: string | null;
  sfx: string | null;
};

export type VideoProps = {
  videoId: string;
  language: string;
  title: string;
  fps: number;
  width: number;
  height: number;
  durationInSeconds: number;
  narration: string;
  scenes: SceneProps[];
  subtitles: SubtitleCue[];
  palette: Record<string, string>;
  burnSubtitles: boolean;
};

/** Usado pelo script de contrato e pelos valores padrao do Studio. */
export const VIDEO_PROPS_FIELDS: (keyof VideoProps)[] = [
  "videoId",
  "language",
  "title",
  "fps",
  "width",
  "height",
  "durationInSeconds",
  "narration",
  "scenes",
  "subtitles",
  "palette",
  "burnSubtitles",
];

export const SCENE_PROPS_FIELDS: (keyof SceneProps)[] = [
  "index",
  "background",
  "start",
  "duration",
  "camera",
  "character",
  "layers",
  "music",
  "sfx",
];

export const CHARACTER_PROPS_FIELDS: (keyof CharacterProps)[] = [
  "pose",
  "svg",
  "position",
];

export const SUBTITLE_CUE_FIELDS: (keyof SubtitleCue)[] = [
  "start",
  "end",
  "text",
];
