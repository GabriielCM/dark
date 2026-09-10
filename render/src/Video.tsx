import React from "react";
import { AbsoluteFill, Audio, staticFile } from "remotion";
import { SceneSequence } from "./components/Scene";
import { Subtitles } from "./components/Subtitles";
import type { VideoProps } from "./types";

/**
 * A composicao. Recebe as props escritas pelo Python (ADR 0001) e monta o
 * video inteiro: cenas com movimento 2.5D, narracao e, opcionalmente, legenda
 * embutida.
 */

export const Video: React.FC<VideoProps> = ({
  scenes,
  subtitles,
  narration,
  fps,
  palette,
  burnSubtitles,
}) => {
  const background = palette?.carvao ?? "#22201D";

  return (
    <AbsoluteFill style={{ backgroundColor: background }}>
      <SceneSequence scenes={scenes} fps={fps} />
      {narration ? <Audio src={staticFile(narration)} /> : null}
      {burnSubtitles ? <Subtitles cues={subtitles} /> : null}
    </AbsoluteFill>
  );
};
