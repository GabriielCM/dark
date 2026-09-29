import React from "react";
import { Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import type { HostProps } from "../types";

/**
 * O MC recortado, de corpo inteiro, sobreposto a cena ou ao cartao
 * explicativo (docs/estilo/analise-entregas.md). O recorte vem da etapa de
 * cenarios, com o figurino do video.
 */

const HEIGHT_FRACTION = 0.62;
const MARGIN_FRACTION = 0.035;

/** Onde o recorte fica no quadro e onde esta a cabeca, em pixels. */
export const hostGeometry = (host: HostProps, width: number, height: number) => {
  const h = height * HEIGHT_FRACTION;
  const w = h * host.aspect;
  const left = host.side === "esquerda" ? width * MARGIN_FRACTION : width * (1 - MARGIN_FRACTION) - w;
  const top = height - h;
  return {
    left,
    top,
    width: w,
    height: h,
    head: { x: left + host.headX * w, y: top + host.headY * h },
  };
};

export const Host: React.FC<{ host: HostProps }> = ({ host }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const geometry = hostGeometry(host, width, height);

  // Entrada com mola: o MC chega, nao aparece.
  const entrance = spring({ frame, fps, config: { damping: 14, mass: 0.6 } });
  const translateY = interpolate(entrance, [0, 1], [50, 0]);
  const opacity = interpolate(entrance, [0, 1], [0, 1]);
  // Respiracao: 4 s por ciclo, deslocamento sutil.
  const breath = Math.sin((frame / fps) * ((Math.PI * 2) / 4)) * 3;

  return (
    <Img
      src={staticFile(host.image)}
      style={{
        position: "absolute",
        left: geometry.left,
        top: geometry.top,
        height: geometry.height,
        width: geometry.width,
        opacity,
        transform: `translateY(${translateY + breath}px)`,
        filter: "drop-shadow(0 6px 10px rgba(0,0,0,0.25))",
      }}
    />
  );
};
