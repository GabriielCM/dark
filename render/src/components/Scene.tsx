import React from "react";
import { AbsoluteFill, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { KenBurns } from "./KenBurns";
import { Character } from "./Character";
import type { SceneProps } from "../types";

/**
 * Uma cena: cenario com movimento 2.5D, gradiente de profundidade e, as vezes,
 * o personagem.
 *
 * O `layers` do storyboard descreve frente/meio/fundo. Sem separacao real das
 * camadas (que exigiria mapa de profundidade), o parallax vem do gradiente
 * sutil que da peso ao primeiro plano — barato e suficiente na fase 1.
 */

const FADE_FRAMES = 12;

export const Scene: React.FC<{ scene: SceneProps; fps: number }> = ({ scene, fps }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const durationInFrames = Math.max(1, Math.round(scene.duration * fps));

  // Cruzamento suave nas bordas da cena: corte seco a cada 9 s cansa.
  const opacity = interpolate(
    frame,
    [0, FADE_FRAMES, durationInFrames - FADE_FRAMES, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );

  return (
    <AbsoluteFill style={{ opacity }}>
      <KenBurns
        src={staticFile(scene.background)}
        camera={scene.camera}
        durationInFrames={durationInFrames}
      />
      {/* Profundidade: escurece topo e base, aproxima o primeiro plano. */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(34,32,29,0.28) 0%, rgba(34,32,29,0) 28%, " +
            "rgba(34,32,29,0) 62%, rgba(34,32,29,0.35) 100%)",
          width,
          height,
        }}
      />
      {scene.character ? <Character character={scene.character} /> : null}
    </AbsoluteFill>
  );
};

export const SceneSequence: React.FC<{ scenes: SceneProps[]; fps: number }> = ({ scenes, fps }) => (
  <>
    {scenes.map((scene) => (
      <Sequence
        key={scene.index}
        from={Math.round(scene.start * fps)}
        durationInFrames={Math.max(1, Math.round(scene.duration * fps))}
        name={`Cena ${scene.index}`}
      >
        <Scene scene={scene} fps={fps} />
      </Sequence>
    ))}
  </>
);
