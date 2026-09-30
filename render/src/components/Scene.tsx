import React from "react";
import { AbsoluteFill, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { SceneProps } from "../types";
import { ExplainerCard } from "./ExplainerCard";
import { Host } from "./Host";
import { KenBurns } from "./KenBurns";

/**
 * Uma cena: o cenario com movimento 2.5D, ou o cartao explicativo sobre a
 * cena anterior desfocada, e, quando a cena pede, o MC recortado ao lado.
 */

const FADE_FRAMES = 12;

export const Scene: React.FC<{ scene: SceneProps; fps: number; font: string }> = ({
  scene,
  fps,
  font,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationInFrames = Math.max(1, Math.round(scene.duration * fps));

  // Cruzamento suave nas bordas da cena: corte seco a cada 6 s cansa.
  const opacity = interpolate(
    frame,
    [0, FADE_FRAMES, durationInFrames - FADE_FRAMES, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ opacity }}>
      {scene.card ? (
        <ExplainerCard background={scene.background} card={scene.card} host={scene.host} font={font} />
      ) : (
        <>
          <KenBurns
            src={staticFile(scene.background)}
            camera={scene.camera}
            durationInFrames={durationInFrames}
            // Com o MC num lado, o assunto esta nos outros dois tercos: o zoom
            // parte dali, e nao do centro, para nao empurrar o assunto para baixo dele.
            focusX={scene.host ? (scene.host.side === "esquerda" ? 0.62 : 0.38) : 0.5}
          />
          {/* Profundidade: escurece topo e base, aproxima o primeiro plano. */}
          <AbsoluteFill
            style={{
              background:
                "linear-gradient(180deg, rgba(34,32,29,0.22) 0%, rgba(34,32,29,0) 26%, " +
                "rgba(34,32,29,0) 64%, rgba(34,32,29,0.3) 100%)",
              width,
              height,
            }}
          />
        </>
      )}
      {scene.host ? <Host host={scene.host} /> : null}
    </AbsoluteFill>
  );
};

export const SceneSequence: React.FC<{ scenes: SceneProps[]; fps: number; font: string }> = ({
  scenes,
  fps,
  font,
}) => (
  <>
    {scenes.map((scene) => (
      <Sequence
        key={scene.index}
        from={Math.round(scene.start * fps)}
        durationInFrames={Math.max(1, Math.round(scene.duration * fps))}
        name={`Cena ${scene.index} (${scene.kind})`}
      >
        <Scene scene={scene} fps={fps} font={font} />
      </Sequence>
    ))}
  </>
);
