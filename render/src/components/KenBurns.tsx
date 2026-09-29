import React from "react";
import { Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CameraMove } from "../types";

/**
 * Movimento 2.5D sobre uma imagem parada (brief 5.3).
 *
 * `overscan` garante que, mesmo no extremo do pan, a imagem cobre o quadro
 * inteiro. `Img` (e nao `img`) faz o Remotion esperar a imagem carregar:
 * sem isso, o primeiro quadro da cena pode sair em branco.
 */

const ZOOM_MIN = 1.0;
const ZOOM_MAX = 1.12;
const PAN_MAX_PX = 90;

export const KenBurns: React.FC<{
  src: string;
  camera: CameraMove;
  durationInFrames: number;
  children?: React.ReactNode;
}> = ({ src, camera, durationInFrames, children }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  let scale = ZOOM_MIN;
  let translateX = 0;

  switch (camera) {
    case "zoom_in":
      scale = interpolate(progress, [0, 1], [ZOOM_MIN, ZOOM_MAX]);
      break;
    case "zoom_out":
      scale = interpolate(progress, [0, 1], [ZOOM_MAX, ZOOM_MIN]);
      break;
    case "pan_left":
      scale = ZOOM_MAX;
      translateX = interpolate(progress, [0, 1], [PAN_MAX_PX, -PAN_MAX_PX]);
      break;
    case "pan_right":
      scale = ZOOM_MAX;
      translateX = interpolate(progress, [0, 1], [-PAN_MAX_PX, PAN_MAX_PX]);
      break;
    case "estatica":
    default:
      // Nem toda cena precisa de movimento. Uma imagem parada depois de um pan
      // longo e uma pausa, nao um defeito.
      scale = ZOOM_MIN + 0.01;
      break;
  }

  // O pan desloca em pixels; a escala precisa cobrir esse deslocamento.
  const overscan = 1 + (PAN_MAX_PX * 2) / width;

  return (
    <div style={{ width, height, overflow: "hidden", position: "absolute" }}>
      <Img
        src={src}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale * overscan}) translateX(${translateX}px)`,
          transformOrigin: "center center",
        }}
      />
      {children}
    </div>
  );
};
