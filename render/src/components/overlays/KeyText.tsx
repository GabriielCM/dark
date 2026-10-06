import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { VERTICAL, isVertical } from "../../layout";
import { INK, outline } from "./style";

/**
 * Texto-chave: numeros, nomes e termos latinos, no terco inferior. Na tela em
 * pe, no alto, abaixo do gancho: o meio e da legenda e o pe e do MC.
 */
export const KeyText: React.FC<{ text: string; font: string; durationInFrames: number }> = ({
  text,
  font,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const vertical = isVertical(width, height);
  const pop = spring({ frame, fps, config: { damping: 11, mass: 0.5 } });
  const opacity = interpolate(frame, [durationInFrames - 10, durationInFrames], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const size = Math.round(width * (vertical ? 0.068 : 0.036));
  const place: React.CSSProperties = vertical
    ? { top: height * VERTICAL.keyText, left: "6%", width: "88%" }
    : { bottom: "16%", width: "100%" };

  return (
    <div
      style={{
        position: "absolute",
        ...place,
        lineHeight: 1.15,
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
