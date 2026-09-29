import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { INK, outline } from "./style";

/** Texto-chave: numeros, nomes e termos latinos, no terco inferior. */
export const KeyText: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 11, mass: 0.5 } });
  const opacity = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const size = Math.round(width * 0.036);

  return (
    <div
      style={{
        position: "absolute",
        bottom: "16%",
        width: "100%",
        textAlign: "center",
        opacity,
        transform: `scale(${interpolate(pop, [0, 1], [0.6, 1])})`,
        fontFamily: font,
        fontWeight: 700,
        fontSize: size,
        color: "#FFFFFF",
        textShadow: outline(INK, size * 0.06),
      }}
    >
      {text}
    </div>
  );
};
