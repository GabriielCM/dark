import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SAFE, isVertical } from "../../layout";
import { INK } from "./style";

/**
 * Balao de fala do MC: comentario curto, nao narrado.
 *
 * `anchor` e a cabeca de quem fala, em pixels. O balao fica acima dela, com o
 * rabicho apontando para baixo, e nunca sai do quadro.
 */
export const SpeechBubble: React.FC<{
  text: string;
  font: string;
  durationInFrames: number;
  anchor: { x: number; y: number };
}> = ({ text, font, durationInFrames, anchor }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 13, mass: 0.5 } });
  const opacity = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  // Na tela em pe o balao cresce e respeita os botoes do app na direita.
  const vertical = isVertical(width, height);
  const size = Math.round(width * (vertical ? 0.04 : 0.0165));
  const maxWidth = Math.round(width * (vertical ? 0.62 : 0.3));
  const tail = Math.round(size * 1.1);
  const gap = Math.round(height * (vertical ? 0.015 : 0.035));
  const rightEdge = width * (vertical ? 1 - SAFE.right : 0.98);
  // Estimativa da largura para centralizar sobre a cabeca sem sair do quadro.
  const estimated = Math.min(maxWidth, text.length * size * 0.55 + size * 1.6);
  const left = Math.min(Math.max(anchor.x - estimated / 2, width * 0.02), rightEdge - estimated);
  const bottom = height - anchor.y + gap + tail;
  const tailX = Math.min(Math.max(anchor.x - left, size), estimated - size);

  return (
    <div
      style={{
        position: "absolute",
        left,
        bottom,
        width: estimated,
        opacity,
        transform: `scale(${interpolate(pop, [0, 1], [0.7, 1])})`,
        transformOrigin: `${tailX}px 100%`,
      }}
    >
      <div
        style={{
          background: "#FFFFFF",
          border: `3px solid ${INK}`,
          borderRadius: size * 1.4,
          padding: `${Math.round(size * 0.45)}px ${Math.round(size * 0.8)}px`,
          fontFamily: font,
          fontWeight: 400,
          fontSize: size,
          lineHeight: 1.2,
          color: INK,
          textAlign: "center",
          boxShadow: "0 3px 8px rgba(0,0,0,0.2)",
        }}
      >
        {text}
      </div>
      <svg
        width={tail * 1.4}
        height={tail}
        style={{ position: "absolute", left: tailX - tail * 0.7, top: "100%", marginTop: -3 }}
      >
        <polygon
          points={`0,0 ${tail * 1.4},0 ${tail * 0.7},${tail}`}
          fill="#FFFFFF"
          stroke={INK}
          strokeWidth={3}
        />
        {/* Cobre o traco de cima para o rabicho sair do balao sem emenda. */}
        <rect x={3} y={0} width={tail * 1.4 - 6} height={3} fill="#FFFFFF" />
      </svg>
    </div>
  );
};
