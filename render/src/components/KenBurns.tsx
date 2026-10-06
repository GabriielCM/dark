import React from "react";
import { Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { isVertical } from "../layout";
import type { CameraMove } from "../types";

/**
 * Movimento 2.5D sobre uma imagem parada (brief 5.3).
 *
 * `overscan` garante que, mesmo no extremo do pan, a imagem cobre o quadro
 * inteiro. `Img` (e nao `img`) faz o Remotion esperar a imagem carregar:
 * sem isso, o primeiro quadro da cena pode sair em branco.
 *
 * Na tela em pe (cortes do TikTok, ADR 0010), a imagem 16:9 enche a altura e
 * so um terco dela cabe na largura: a camera corre de lado, devagar, pela
 * parte do assunto, em vez de cortar o centro e parar.
 */

const ZOOM_MIN = 1.0;
const ZOOM_MAX = 1.12;
const PAN_MAX_PX = 90;
/** Proporcao dos cenarios gerados (1920x1088). */
const IMAGE_ASPECT = 16 / 9;
/** Quanto a camera anda na tela em pe, em fracao da largura da imagem. */
const VERTICAL_PAN = 0.24;
const VERTICAL_DRIFT = 0.08;
const VERTICAL_ZOOM = 1.08;

const VerticalPan: React.FC<{
  src: string;
  camera: CameraMove;
  progress: number;
  focusX: number;
  width: number;
  height: number;
}> = ({ src, camera, progress, focusX, width, height }) => {
  let zoom = 1;
  let from = focusX - VERTICAL_DRIFT / 2;
  let to = focusX + VERTICAL_DRIFT / 2;
  switch (camera) {
    case "pan_left":
      from = focusX + VERTICAL_PAN / 2;
      to = focusX - VERTICAL_PAN / 2;
      break;
    case "pan_right":
      from = focusX - VERTICAL_PAN / 2;
      to = focusX + VERTICAL_PAN / 2;
      break;
    case "zoom_in":
      zoom = interpolate(progress, [0, 1], [1, VERTICAL_ZOOM]);
      break;
    case "zoom_out":
      zoom = interpolate(progress, [0, 1], [VERTICAL_ZOOM, 1]);
      [from, to] = [to, from];
      break;
    case "estatica":
    default:
      break;
  }
  const boxHeight = height * zoom;
  const boxWidth = boxHeight * IMAGE_ASPECT;
  const focus = interpolate(progress, [0, 1], [from, to]);
  // O ponto `focus` da imagem fica no centro do quadro, sem mostrar a borda.
  const left = Math.min(0, Math.max(width - boxWidth, width / 2 - focus * boxWidth));
  return (
    <div
      style={{
        position: "absolute",
        left,
        top: (height - boxHeight) / 2,
        width: boxWidth,
        height: boxHeight,
      }}
    >
      <Img src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
    </div>
  );
};

export const KenBurns: React.FC<{
  src: string;
  camera: CameraMove;
  durationInFrames: number;
  /** Ponto horizontal fixo do zoom, de 0 a 1 (0,5: o centro). */
  focusX?: number;
  children?: React.ReactNode;
}> = ({ src, camera, durationInFrames, focusX = 0.5, children }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (isVertical(width, height)) {
    return (
      <div style={{ width, height, overflow: "hidden", position: "absolute" }}>
        <VerticalPan
          src={src}
          camera={camera}
          progress={progress}
          focusX={focusX}
          width={width}
          height={height}
        />
        {children}
      </div>
    );
  }

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
          transformOrigin: `${(focusX * 100).toFixed(1)}% 50%`,
        }}
      />
      {children}
    </div>
  );
};
