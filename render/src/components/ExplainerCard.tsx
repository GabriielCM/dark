import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { VERTICAL, isVertical } from "../layout";
import type { CardProps, HostProps } from "../types";
import { INK, PAPER, labelBox } from "./overlays/style";

/**
 * Cartao explicativo (docs/estilo/analise-entregas.md): a cena anterior
 * desfocada ao fundo, papel creme com hachura por cima, uma ou duas pecas
 * recortadas com rotulo e, na comparacao, a divisoria tracejada.
 */
export const ExplainerCard: React.FC<{
  background: string;
  card: CardProps;
  host: HostProps | null;
  font: string;
}> = ({ background, card, host, font }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();

  // A area das pecas deixa livre o lado do MC recortado. Na tela em pe, o MC
  // fica no pe do quadro e as pecas ocupam a faixa entre o gancho e a legenda.
  const vertical = isVertical(width, height);
  const hostLeft = host?.side === "esquerda";
  const areaLeft = vertical
    ? width * 0.05
    : host
      ? hostLeft
        ? width * 0.28
        : width * 0.04
      : width * 0.08;
  const areaWidth = vertical ? width * 0.9 : host ? width * 0.68 : width * 0.84;
  const areaTop = vertical ? height * VERTICAL.card.top : height * 0.12;
  const areaHeight = vertical ? height * VERTICAL.card.height : height * 0.76;
  const count = card.pieces.length;
  const slot = areaWidth / count;
  const pieceHeight = vertical
    ? areaHeight * 0.72
    : height * (count === 1 ? 0.56 : 0.46);
  const labelSize = Math.round(width * (vertical ? 0.034 : 0.016));

  return (
    <AbsoluteFill>
      <Img
        src={staticFile(background)}
        style={{
          position: "absolute",
          width: "100%",
          height: "100%",
          objectFit: "cover",
          filter: "blur(16px) saturate(0.8)",
          transform: "scale(1.12)",
        }}
      />
      <AbsoluteFill
        style={{
          backgroundColor: PAPER,
          opacity: 0.84,
          backgroundImage:
            "repeating-linear-gradient(135deg, rgba(34,32,29,0.07) 0px, rgba(34,32,29,0.07) 2px, transparent 2px, transparent 26px)",
        }}
      />
      {card.pieces.map((piece, i) => {
        const pop = spring({ frame: frame - i * 6, fps, config: { damping: 13, mass: 0.6 } });
        const centerX = areaLeft + slot * (i + 0.5);
        return (
          <div
            key={piece.image}
            style={{
              position: "absolute",
              left: centerX - slot * 0.45,
              width: slot * 0.9,
              top: areaTop,
              height: areaHeight,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: height * (vertical ? 0.015 : 0.035),
              opacity: interpolate(pop, [0, 1], [0, 1]),
              transform: `scale(${interpolate(pop, [0, 1], [0.8, 1])})`,
            }}
          >
            <Img
              src={staticFile(piece.image)}
              style={{ maxHeight: pieceHeight, maxWidth: slot * 0.85, objectFit: "contain" }}
            />
            {piece.label ? <div style={labelBox(font, labelSize)}>{piece.label}</div> : null}
          </div>
        );
      })}
      {card.comparison && count === 2 ? (
        <div
          style={{
            position: "absolute",
            left: areaLeft + slot,
            top: vertical ? areaTop + areaHeight * 0.03 : height * 0.14,
            height: vertical ? areaHeight * 0.94 : height * 0.72,
            borderLeft: `3px dashed ${INK}`,
            opacity: 0.55,
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
};
