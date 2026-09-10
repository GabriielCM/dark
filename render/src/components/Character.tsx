import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { CharacterProps } from "../types";

/**
 * Personagem recorrente, vindo da biblioteca SVG (brief 5.2).
 *
 * A biblioteca e gerada uma unica vez; aqui so se posiciona e anima. Enquanto
 * o personagem nao existir (decisao pendente do brief, secao 12), `svg` vem
 * nulo e a cena simplesmente sai sem ele.
 */

export const Character: React.FC<{ character: CharacterProps }> = ({ character }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  if (!character.svg) {
    return null;
  }

  // Entrada com mola: o personagem chega, nao aparece.
  const entrance = spring({ frame, fps, config: { damping: 14, mass: 0.6 } });
  const translateY = interpolate(entrance, [0, 1], [40, 0]);
  const opacity = interpolate(entrance, [0, 1], [0, 1]);
  // Respiracao: 4 s por ciclo, deslocamento sutil.
  const breath = Math.sin((frame / fps) * ((Math.PI * 2) / 4)) * 4;

  const horizontal =
    character.position === "esquerda"
      ? { left: width * 0.06 }
      : character.position === "centro"
        ? { left: width * 0.5 - height * 0.22 }
        : { right: width * 0.06 };

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        height: height * 0.55,
        opacity,
        transform: `translateY(${translateY + breath}px)`,
        ...horizontal,
      }}
    >
      <Img src={staticFile(character.svg)} style={{ height: "100%" }} />
    </div>
  );
};
