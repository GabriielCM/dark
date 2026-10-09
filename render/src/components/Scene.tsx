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

const ramp = (frame: number, range: [number, number], output: [number, number]) =>
  interpolate(frame, range, output, { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

export const Scene: React.FC<{
  scene: SceneProps;
  /** Quadro do video em que a cena comeca. */
  startFrame: number;
  durationInFrames: number;
  /** O MC ja estava na cena anterior, no mesmo lugar: nao entra de novo. */
  hostEnters: boolean;
  font: string;
}> = ({ scene, startFrame, durationInFrames, hostEnters, font }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  // Corte seco entre as cenas de um capitulo, com imagem a cada ~3 s; o
  // escurecimento fica so na troca de capitulo (ADR 0012). O fade cabe em
  // um terco da cena: numa cena curta, o intervalo do interpolate continua
  // crescente.
  const fade = Math.max(1, Math.min(FADE_FRAMES, Math.floor(durationInFrames / 3)));
  const opacity = Math.min(
    scene.fadeIn ? ramp(frame, [0, fade], [0, 1]) : 1,
    scene.fadeOut ? ramp(frame, [durationInFrames - fade, durationInFrames], [1, 0]) : 1,
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
      {scene.host ? <Host host={scene.host} enters={hostEnters} startFrame={startFrame} /> : null}
    </AbsoluteFill>
  );
};

const sameHost = (a: SceneProps | undefined, b: SceneProps): boolean =>
  !!a?.host && !!b.host && a.host.image === b.host.image && a.host.side === b.host.side;

export const SceneSequence: React.FC<{ scenes: SceneProps[]; fps: number; font: string }> = ({
  scenes,
  fps,
  font,
}) => (
  <>
    {scenes.map((scene, i) => {
      // O fim de uma cena e o comeco da proxima, arredondados do mesmo jeito:
      // arredondar inicio e duracao separados abre um quadro vazio, que no
      // corte seco pisca.
      const from = Math.round(scene.start * fps);
      const next = scenes[i + 1];
      const to = next ? Math.round(next.start * fps) : Math.round((scene.start + scene.duration) * fps);
      const durationInFrames = Math.max(1, to - from);
      const previous = scenes[i - 1];
      return (
        <Sequence
          key={`${scene.index}-${i}`}
          from={from}
          durationInFrames={durationInFrames}
          name={`Cena ${scene.index} (${scene.kind})`}
        >
          <Scene
            scene={scene}
            startFrame={from}
            durationInFrames={durationInFrames}
            hostEnters={scene.fadeIn || !sameHost(previous, scene)}
            font={font}
          />
        </Sequence>
      );
    })}
  </>
);
