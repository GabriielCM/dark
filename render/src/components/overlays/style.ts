/**
 * Pecas de estilo das camadas, tiradas dos videos entregues
 * (docs/estilo/analise-entregas.md).
 */
import type React from "react";

export const INK = "#22201D";
export const TERRACOTA = "#B8583A";
export const PAPER = "#F5EFE2";

/** Contorno grosso em volta do texto (sombra em anel: funciona em qualquer navegador). */
export const outline = (color: string, px: number): string => {
  const shadows: string[] = [];
  const steps = 16;
  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * Math.PI * 2;
    shadows.push(
      `${(Math.cos(angle) * px).toFixed(1)}px ${(Math.sin(angle) * px).toFixed(1)}px 0 ${color}`,
    );
  }
  return shadows.join(", ");
};

export const labelBox = (font: string, size: number): React.CSSProperties => ({
  fontFamily: font,
  fontWeight: 700,
  fontSize: size,
  textTransform: "uppercase",
  letterSpacing: 1,
  color: INK,
  background: "#FFFFFF",
  border: `3px solid ${INK}`,
  padding: `${Math.round(size * 0.18)}px ${Math.round(size * 0.55)}px`,
  whiteSpace: "nowrap",
});
