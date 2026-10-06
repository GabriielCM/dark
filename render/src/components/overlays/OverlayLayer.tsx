import React from "react";
import { Sequence, useVideoConfig } from "remotion";
import { VERTICAL, isVertical } from "../../layout";
import type { OverlayCue, SceneProps } from "../../types";
import { hostGeometry } from "../Host";
import { ChapterTitle } from "./ChapterTitle";
import { EndCard } from "./EndCard";
import { HookCard } from "./HookCard";
import { KeyText } from "./KeyText";
import { LocationTag } from "./LocationTag";
import { SpeechBubble } from "./SpeechBubble";

/**
 * Linha do tempo das camadas. Titulo, tarja, texto-chave e balao tem tempo
 * proprio: um titulo de capitulo atravessa varias cenas. Gancho e cartao do
 * fim so existem nos cortes do TikTok (ADR 0010).
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
    if (isVertical(width, height)) {
      // Na tela em pe o recorte da imagem nao mostra onde o MC desenhado esta:
      // o balao fica entre o texto-chave e a legenda.
      return { x: VERTICAL.actedAnchor.x * width, y: VERTICAL.actedAnchor.y * height };
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
            {cue.kind === "gancho" ? <HookCard {...props} /> : null}
            {cue.kind === "fim" ? <EndCard {...props} /> : null}
          </Sequence>
        );
      })}
    </>
  );
};
