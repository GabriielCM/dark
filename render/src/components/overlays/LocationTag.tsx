import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { VERTICAL, isVertical } from "../../layout";
import { INK, TERRACOTA } from "./style";

/**
 * Tarja de local e epoca: caixa terracota, texto branco, centro inferior. Na
 * tela em pe, no alto: o pe e da legenda do post no app.
 */
export const LocationTag: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const vertical = isVertical(width, height);
  const enter = spring({ frame, fps, config: { damping: 20 } });
  const opacity = interpolate(
    frame,
    [0, 6, durationInFrames - 10, durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const size = Math.round(width * (vertical ? 0.034 : 0.018));
  const place: React.CSSProperties = vertical
    ? { top: height * VERTICAL.topBand }
    : { bottom: "7%" };

  return (
    <div
      style={{
        position: "absolute",
        ...place,
        width: "100%",
        display: "flex",
        justifyContent: "center",
        opacity,
        transform: `translateY(${interpolate(enter, [0, 1], [24, 0])}px)`,
      }}
    >
      <div
        style={{
          background: TERRACOTA,
          border: `3px solid ${INK}`,
          color: "#FFFFFF",
          fontFamily: font,
          fontWeight: 700,
          fontSize: size,
          letterSpacing: 1.5,
          textTransform: "uppercase",
          padding: `${Math.round(size * 0.3)}px ${Math.round(size * 0.9)}px`,
          boxShadow: "0 4px 10px rgba(0,0,0,0.25)",
        }}
      >
        {text}
      </div>
    </div>
  );
};
