import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { INK, outline } from "./style";

/** Largura da faixa do titulo: nunca de borda a borda (amostra de 29/09). */
const MAX_WIDTH = 0.84;
/** Tamanho dos videos entregues: maiusculas com ~8% da altura do quadro. */
const BASE_SIZE = 0.055;
const MIN_SIZE = 0.03;
const LETTER_SPACING = 2;
/**
 * Largura media de uma letra em caixa alta, em em. Medido na Comic Relief em
 * negrito: 0,65 a 0,70; com folga para nao encostar na borda.
 */
const EM_PER_CHAR = 0.72;

/**
 * Titulo do capitulo: topo, caixa alta, branco com contorno escuro, numa linha.
 *
 * O texto e o trecho curto do titulo (antes dos dois-pontos, ver
 * text/titles.py). Se ainda assim for largo demais, a fonte encolhe ate caber
 * na faixa. A largura e estimada, como no balao: medir no DOM antes de a fonte
 * carregar daria a largura da fonte de reserva.
 */
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
  const band = width * MAX_WIDTH;
  const chars = Math.max(text.length, 1);
  const fitted = (band - chars * LETTER_SPACING) / (chars * EM_PER_CHAR);
  const size = Math.round(Math.max(width * MIN_SIZE, Math.min(width * BASE_SIZE, fitted)));

  return (
    <div
      style={{
        position: "absolute",
        top: "5%",
        left: (width - band) / 2,
        width: band,
        textAlign: "center",
        whiteSpace: "nowrap",
        opacity,
        transform: `translateY(${interpolate(enter, [0, 1], [-30, 0])}px)`,
        fontFamily: font,
        fontWeight: 700,
        fontSize: size,
        letterSpacing: LETTER_SPACING,
        textTransform: "uppercase",
        color: "#FFFFFF",
        textShadow: `${outline(INK, size * 0.07)}, 0 ${size * 0.08}px ${size * 0.12}px rgba(0,0,0,0.35)`,
      }}
    >
      {text}
    </div>
  );
};
