import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { DecodedImg } from "./DecodedImg";
import { isVertical } from "../layout";
import type { CameraMove } from "../types";

/**
 * Movimento 2.5D sobre uma imagem parada (brief 5.3).
 *
 * `overscan` garante que, mesmo no extremo do pan, a imagem cobre o quadro
 * inteiro. `DecodedImg` (e nao `img` nem o `Img` do Remotion) faz o quadro
 * esperar a imagem decodificada e pintada: sem isso, a troca de cena pisca.
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
/**
 * Cena em que o movimento anda inteiro. Numa cena mais curta (o ritmo de ~3 s
 * do ADR 0012), a amplitude encolhe junto, ate a metade: a camera mantem a
 * velocidade, em vez de correr o mesmo caminho na metade do tempo.
 */
const MOTION_FULL_S = 6;
const MOTION_MIN = 0.5;

const VerticalPan: React.FC<{
  src: string;
  camera: CameraMove;
  progress: number;
  amount: number;
  focusX: number;
  width: number;
  height: number;
}> = ({ src, camera, progress, amount, focusX, width, height }) => {
  const pan = VERTICAL_PAN * amount;
  const drift = VERTICAL_DRIFT * amount;
  const maxZoom = 1 + (VERTICAL_ZOOM - 1) * amount;
  let zoom = 1;
  let from = focusX - drift / 2;
  let to = focusX + drift / 2;
  switch (camera) {
    case "pan_left":
      from = focusX + pan / 2;
      to = focusX - pan / 2;
      break;
    case "pan_right":
      from = focusX - pan / 2;
      to = focusX + pan / 2;
      break;
    case "zoom_in":
      zoom = interpolate(progress, [0, 1], [1, maxZoom]);
      break;
    case "zoom_out":
      zoom = interpolate(progress, [0, 1], [maxZoom, 1]);
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
      <DecodedImg src={src} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
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
  const { width, height, fps } = useVideoConfig();
  const progress = interpolate(frame, [0, Math.max(durationInFrames - 1, 1)], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const amount = Math.min(1, Math.max(MOTION_MIN, durationInFrames / fps / MOTION_FULL_S));
  const zoomMax = ZOOM_MIN + (ZOOM_MAX - ZOOM_MIN) * amount;
  const panPx = PAN_MAX_PX * amount;

  if (isVertical(width, height)) {
    return (
      <div style={{ width, height, overflow: "hidden", position: "absolute" }}>
        <VerticalPan
          src={src}
          camera={camera}
          progress={progress}
          amount={amount}
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
      scale = interpolate(progress, [0, 1], [ZOOM_MIN, zoomMax]);
      break;
    case "zoom_out":
      scale = interpolate(progress, [0, 1], [zoomMax, ZOOM_MIN]);
      break;
    case "pan_left":
      scale = ZOOM_MAX;
      translateX = interpolate(progress, [0, 1], [panPx, -panPx]);
      break;
    case "pan_right":
      scale = ZOOM_MAX;
      translateX = interpolate(progress, [0, 1], [-panPx, panPx]);
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
      <DecodedImg
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
