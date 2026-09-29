import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { FONT_FAMILIES, fontStack } from "./fonts";
import { INK, TERRACOTA, labelBox, outline } from "./components/overlays/style";

/**
 * Quadro para escolher a fonte das camadas: as tres candidatas lado a lado,
 * cada uma com titulo, tarja, texto-chave, rotulo e balao, sobre um cenario.
 *
 *   npx remotion still src/index.ts FontBoard saida.png --props=... --public-dir=...
 */
export type FontBoardProps = { background: string };

export const FontBoard: React.FC<FontBoardProps> = ({ background }) => (
  <AbsoluteFill style={{ backgroundColor: "#111" }}>
    {background ? (
      <Img
        src={staticFile(background)}
        style={{ position: "absolute", width: "100%", height: "100%", objectFit: "cover", opacity: 0.55 }}
      />
    ) : null}
    <AbsoluteFill style={{ flexDirection: "row" }}>
      {FONT_FAMILIES.map((family) => {
        const font = fontStack(family);
        return (
          <div
            key={family}
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 36,
              paddingTop: 40,
              borderRight: "2px solid rgba(255,255,255,0.35)",
            }}
          >
            <div style={{ fontFamily: "Arial", fontSize: 30, color: "#fff", background: "rgba(0,0,0,0.55)", padding: "6px 18px" }}>
              {family}
            </div>
            <div
              style={{
                fontFamily: font,
                fontWeight: 700,
                fontSize: 58,
                color: "#fff",
                textTransform: "uppercase",
                textShadow: outline(INK, 4),
                textAlign: "center",
                lineHeight: 1.05,
              }}
            >
              Antes do sol
            </div>
            <div
              style={{
                background: TERRACOTA,
                border: `3px solid ${INK}`,
                color: "#fff",
                fontFamily: font,
                fontWeight: 700,
                fontSize: 26,
                padding: "8px 22px",
                textTransform: "uppercase",
              }}
            >
              Acampamento romano, século I
            </div>
            <div style={{ fontFamily: font, fontWeight: 700, fontSize: 54, color: "#fff", textShadow: outline(INK, 3.5) }}>
              16.800 homens
            </div>
            <div style={labelBox(font, 26)}>Dolabra</div>
            <div
              style={{
                background: "#fff",
                border: `3px solid ${INK}`,
                borderRadius: 36,
                padding: "12px 24px",
                fontFamily: font,
                fontSize: 30,
                color: INK,
                maxWidth: 520,
                textAlign: "center",
              }}
            >
              Isso pesa mais do que parece.
            </div>
            <div style={{ fontFamily: font, fontSize: 26, color: "#fff", textShadow: outline(INK, 2), textAlign: "center", padding: "0 30px" }}>
              ÁÉÍÓÚ ÂÊÔ ÃÕ Ç à — acentos e cedilha
            </div>
          </div>
        );
      })}
    </AbsoluteFill>
  </AbsoluteFill>
);
