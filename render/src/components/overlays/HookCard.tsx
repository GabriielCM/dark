import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { VERTICAL } from "../../layout";
import { INK, PAPER, TERRACOTA, outline } from "./style";

/**
 * Gancho do corte do TikTok (ADR 0010): a frase que prende nos primeiros
 * segundos, numa placa creme de borda escura, como a placa do banner do
 * canal. Tirada do proprio trecho, nunca narrada.
 */
export const HookCard: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 12, mass: 0.6 } });
  const opacity = interpolate(frame, [durationInFrames - 8, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const unit = Math.min(width, height);
  // Gancho longo encolhe para caber em tres linhas.
  const size = Math.round(unit * (text.length > 48 ? 0.062 : 0.074));

  return (
    <div
      style={{
        position: "absolute",
        top: height * VERTICAL.topBand,
        left: width * 0.06,
        width: width * 0.88,
        display: "flex",
        justifyContent: "center",
        opacity,
        transform: `scale(${interpolate(pop, [0, 1], [0.7, 1])}) rotate(${interpolate(pop, [0, 1], [-3, -1])}deg)`,
      }}
    >
      <div
        style={{
          background: PAPER,
          border: `${Math.round(size * 0.08)}px solid ${INK}`,
          borderRadius: size * 0.35,
          padding: `${Math.round(size * 0.32)}px ${Math.round(size * 0.48)}px`,
          boxShadow: "0 8px 18px rgba(0,0,0,0.35)",
          fontFamily: font,
          fontWeight: 700,
          fontSize: size,
          lineHeight: 1.12,
          textAlign: "center",
          color: TERRACOTA,
          textShadow: outline(INK, size * 0.045),
        }}
      >
        {text}
      </div>
    </div>
  );
};
