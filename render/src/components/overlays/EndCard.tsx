import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { VERTICAL } from "../../layout";
import { INK, TERRACOTA } from "./style";

/**
 * Cartao dos ultimos segundos do corte do TikTok (ADR 0010): o video
 * completo esta fixado no perfil. Na cor da tarja, para nao competir com o
 * gancho, que e creme.
 */
export const EndCard: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 14 } });
  const opacity = interpolate(frame, [0, 6, durationInFrames - 4, durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const size = Math.round(Math.min(width, height) * 0.052);

  return (
    <div
      style={{
        position: "absolute",
        top: height * VERTICAL.topBand,
        width: "100%",
        display: "flex",
        justifyContent: "center",
        opacity,
        transform: `translateY(${interpolate(enter, [0, 1], [-40, 0])}px)`,
      }}
    >
      <div
        style={{
          maxWidth: width * 0.84,
          background: TERRACOTA,
          border: `${Math.round(size * 0.1)}px solid ${INK}`,
          borderRadius: size * 0.3,
          padding: `${Math.round(size * 0.35)}px ${Math.round(size * 0.7)}px`,
          boxShadow: "0 6px 14px rgba(0,0,0,0.3)",
          color: "#FFFFFF",
          fontFamily: font,
          fontWeight: 700,
          fontSize: size,
          lineHeight: 1.15,
          textAlign: "center",
        }}
      >
        {text}
      </div>
    </div>
  );
};
