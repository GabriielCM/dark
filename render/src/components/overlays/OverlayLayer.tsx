import React from "react";
import { Sequence, useVideoConfig } from "remotion";
import type { OverlayCue, SceneProps } from "../../types";
import { hostGeometry } from "../Host";
import { ChapterTitle } from "./ChapterTitle";
import { KeyText } from "./KeyText";
import { LocationTag } from "./LocationTag";
import { SpeechBubble } from "./SpeechBubble";

/**
 * Linha do tempo das camadas. Titulo, tarja, texto-chave e balao tem tempo
 * proprio: um titulo de capitulo atravessa varias cenas.
 */
export const OverlayLayer: React.FC<{
  overlays: OverlayCue[];
  scenes: SceneProps[];
  font: string;
  fps: number;
}> = ({ overlays, scenes, font, fps }) => {
  const { width, height } = useVideoConfig();

  const anchorFor = (cue: OverlayCue): { x: number; y: number } => {
    const scene = cue.scene !== null ? scenes.find((s) => s.index === cue.scene) : undefined;
    if (scene?.host) {
      return hostGeometry(scene.host, width, height).head;
    }
    return { x: (cue.anchorX ?? 0.62) * width, y: (cue.anchorY ?? 0.3) * height };
  };

  return (
    <>
      {overlays.map((cue, i) => {
        const durationInFrames = Math.max(1, Math.round(cue.duration * fps));
        const props = { text: cue.text, font, durationInFrames };
        return (
          <Sequence
            key={`${cue.kind}-${i}`}
            from={Math.round(cue.start * fps)}
            durationInFrames={durationInFrames}
            name={`${cue.kind}: ${cue.text}`}
            layout="none"
          >
            {cue.kind === "titulo" ? <ChapterTitle {...props} /> : null}
            {cue.kind === "tarja" ? <LocationTag {...props} /> : null}
            {cue.kind === "texto" ? <KeyText {...props} /> : null}
            {cue.kind === "balao" ? <SpeechBubble {...props} anchor={anchorFor(cue)} /> : null}
          </Sequence>
        );
      })}
    </>
  );
};
