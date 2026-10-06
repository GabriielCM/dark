import React from "react";
import { AbsoluteFill, Audio, staticFile } from "remotion";
import { fontStack } from "./fonts";
import { SceneSequence } from "./components/Scene";
import { Subtitles } from "./components/Subtitles";
import { OverlayLayer } from "./components/overlays/OverlayLayer";
import type { VideoProps } from "./types";

/**
 * A composicao. Recebe as props escritas pelo Python (ADR 0001) e monta o
 * video inteiro: cenas com movimento 2.5D ou cartao explicativo, o MC
 * recortado, as camadas com tempo proprio (titulo, tarja, texto-chave,
 * balao), a narracao e, se pedido, a legenda embutida.
 */

export const Video: React.FC<VideoProps> = ({
  scenes,
  overlays,
  subtitles,
  narration,
  fps,
  palette,
  fontFamily,
  burnSubtitles,
}) => {
  const background = palette?.carvao ?? "#22201D";
  const font = fontStack(fontFamily);

  return (
    <AbsoluteFill style={{ backgroundColor: background }}>
      <SceneSequence scenes={scenes} fps={fps} font={font} />
      <OverlayLayer overlays={overlays} scenes={scenes} font={font} fps={fps} />
      {narration ? <Audio src={staticFile(narration)} /> : null}
      {burnSubtitles ? <Subtitles cues={subtitles} font={font} /> : null}
    </AbsoluteFill>
  );
};
