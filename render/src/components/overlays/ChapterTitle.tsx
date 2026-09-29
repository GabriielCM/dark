import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { INK, outline } from "./style";

/** Titulo do capitulo: topo, caixa alta, branco com contorno escuro. */
export const ChapterTitle: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 18, mass: 0.7 } });
  const opacity = interpolate(
    frame,
    [0, 8, durationInFrames - 14, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const size = Math.round(width * 0.046);

  return (
    <div
      style={{
        position: "absolute",
        top: "5%",
        width: "100%",
        textAlign: "center",
        opacity,
        transform: `translateY(${interpolate(enter, [0, 1], [-30, 0])}px)`,
        fontFamily: font,
        fontWeight: 700,
        fontSize: size,
        letterSpacing: 2,
        textTransform: "uppercase",
        color: "#FFFFFF",
        textShadow: `${outline(INK, size * 0.07)}, 0 ${size * 0.08}px ${size * 0.12}px rgba(0,0,0,0.35)`,
      }}
    >
      {text}
    </div>
  );
};
