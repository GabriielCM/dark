import React from "react";
import { Composition } from "remotion";
import { Video } from "./Video";
import type { VideoProps } from "./types";

/**
 * Props de exemplo para o Studio. Na renderizacao de verdade, tudo vem do
 * --props= escrito pelo Python; isto so existe para `npm run studio` abrir
 * mostrando alguma coisa.
 */
const exampleProps: VideoProps = {
  videoId: "exemplo",
  language: "pt-BR",
  title: "Exemplo",
  fps: 30,
  width: 1920,
  height: 1080,
  durationInSeconds: 9,
  narration: "",
  scenes: [
    {
      index: 1,
      background: "",
      start: 0,
      duration: 9,
      camera: "zoom_in",
      character: null,
      layers: [],
      music: null,
      sfx: null,
    },
  ],
  subtitles: [],
  palette: { carvao: "#22201D" },
  burnSubtitles: false,
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Video"
    component={Video}
    durationInFrames={Math.round(exampleProps.durationInSeconds * exampleProps.fps)}
    fps={exampleProps.fps}
    width={exampleProps.width}
    height={exampleProps.height}
    defaultProps={exampleProps}
    // A duracao real vem das props do Python: cada video tem a sua.
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, Math.round(props.durationInSeconds * props.fps)),
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
