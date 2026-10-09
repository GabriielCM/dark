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

export type HostSide = "esquerda" | "direita";

/** `gancho` e `fim` so aparecem nos cortes verticais do TikTok (ADR 0010). */
export type OverlayKind = "titulo" | "tarja" | "texto" | "balao" | "gancho" | "fim";

/** O MC recortado, de corpo inteiro, sobreposto a cena. */
export type HostProps = {
  image: string;
  side: HostSide;
  aspect: number;
  headX: number;
  headY: number;
};

export type CardPiece = {
  image: string;
  label: string;
};

/** Cartao explicativo: pecas com rotulo sobre fundo de papel. */
export type CardProps = {
  pieces: CardPiece[];
  comparison: boolean;
};

export type OverlayCue = {
  kind: OverlayKind;
  start: number;
  duration: number;
  text: string;
  anchorX: number | null;
  anchorY: number | null;
  scene: number | null;
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
  kind: string;
  host: HostProps | null;
  card: CardProps | null;
  /** Escurece ao entrar / ao sair: so na troca de capitulo (ADR 0012). */
  fadeIn: boolean;
  fadeOut: boolean;
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
  overlays: OverlayCue[];
  subtitles: SubtitleCue[];
  palette: Record<string, string>;
  fontFamily: string;
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
  "overlays",
  "subtitles",
  "palette",
  "fontFamily",
  "burnSubtitles",
];

export const SCENE_PROPS_FIELDS: (keyof SceneProps)[] = [
  "index",
  "background",
  "start",
  "duration",
  "camera",
  "kind",
  "host",
  "card",
  "fadeIn",
  "fadeOut",
];

export const HOST_PROPS_FIELDS: (keyof HostProps)[] = ["image", "side", "aspect", "headX", "headY"];

export const CARD_PROPS_FIELDS: (keyof CardProps)[] = ["pieces", "comparison"];

export const CARD_PIECE_FIELDS: (keyof CardPiece)[] = ["image", "label"];

export const OVERLAY_CUE_FIELDS: (keyof OverlayCue)[] = [
  "kind",
  "start",
  "duration",
  "text",
  "anchorX",
  "anchorY",
  "scene",
];

export const SUBTITLE_CUE_FIELDS: (keyof SubtitleCue)[] = ["start", "end", "text"];
