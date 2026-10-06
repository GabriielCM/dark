import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SAFE, VERTICAL, isVertical } from "../layout";
import type { SubtitleCue } from "../types";
import { INK, outline } from "./overlays/style";

/**
 * Legenda embutida, agrupada em blocos legiveis a partir das palavras.
 *
 * O SRT separado continua sendo a entrega principal do YouTube (brief 6.3);
 * isto e para quando se quiser queimar a legenda no video.
 *
 * Nos cortes do TikTok (ADR 0010) a legenda vai sempre queimada, no jeito do
 * app: poucas palavras por vez, grandes, no meio da tela, com a palavra que
 * esta sendo falada em destaque. Muita gente comeca a assistir sem som.
 */

const MAX_CHARS = 42;
/** Tela em pe: ate 3 palavras ou 18 caracteres por vez. */
const VERTICAL_WORDS = 3;
const VERTICAL_CHARS = 18;
/** Pausa na fala que encerra o bloco mesmo antes do limite. */
const VERTICAL_GAP_S = 0.6;
const HIGHLIGHT = "#FFD24A";

type Block = { start: number; end: number; text: string; words: SubtitleCue[] };

const groupCues = (cues: SubtitleCue[]): Block[] => {
  const blocks: Block[] = [];
  let current: SubtitleCue[] = [];

  const flush = () => {
    if (current.length === 0) return;
    blocks.push({
      start: current[0].start,
      end: current[current.length - 1].end,
      text: current.map((c) => c.text).join(" "),
      words: current,
    });
    current = [];
  };

  for (const cue of cues) {
    const length = current.reduce((n, c) => n + c.text.length + 1, 0) + cue.text.length;
    const span = current.length > 0 ? cue.end - current[0].start : 0;
    const endsSentence =
      current.length > 0 && /[.!?]$/.test(current[current.length - 1].text);
    if (current.length > 0 && (length > MAX_CHARS * 2 || span > 6 || endsSentence)) {
      flush();
    }
    current.push(cue);
  }
  flush();
  return blocks;
};

const groupVertical = (cues: SubtitleCue[]): Block[] => {
  const blocks: Block[] = [];
  let current: SubtitleCue[] = [];

  const flush = () => {
    if (current.length === 0) return;
    blocks.push({
      start: current[0].start,
      // O bloco fica na tela ate o proximo comecar: sem piscar entre palavras.
      end: current[current.length - 1].end,
      text: current.map((c) => c.text).join(" "),
      words: current,
    });
    current = [];
  };

  for (const cue of cues) {
    if (current.length > 0) {
      const last = current[current.length - 1];
      const length = current.reduce((n, c) => n + c.text.length + 1, 0) + cue.text.length;
      if (
        current.length >= VERTICAL_WORDS ||
        length > VERTICAL_CHARS ||
        /[.!?,;:]$/.test(last.text) ||
        cue.start - last.end > VERTICAL_GAP_S
      ) {
        flush();
      }
    }
    current.push(cue);
  }
  flush();
  // Estende cada bloco ate o comeco do seguinte (pausas curtas).
  for (let i = 0; i < blocks.length - 1; i++) {
    const next = blocks[i + 1];
    if (next.start - blocks[i].end <= VERTICAL_GAP_S) {
      blocks[i] = { ...blocks[i], end: next.start };
    }
  }
  return blocks;
};

const VerticalSubtitles: React.FC<{ cues: SubtitleCue[]; font: string }> = ({ cues, font }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const time = frame / fps;

  const blocks = React.useMemo(() => groupVertical(cues), [cues]);
  const active = blocks.find((b) => time >= b.start && time < b.end);
  if (!active) return null;

  const size = Math.round(width * 0.085);
  const pop = spring({
    frame: frame - Math.round(active.start * fps),
    fps,
    config: { damping: 14, mass: 0.4 },
  });
  // A palavra em destaque e a ultima que ja comecou.
  let current = 0;
  active.words.forEach((w, i) => {
    if (time >= w.start) current = i;
  });

  return (
    <div
      style={{
        position: "absolute",
        top: height * VERTICAL.subtitles,
        left: width * SAFE.left,
        width: width * (1 - SAFE.left - SAFE.right),
        textAlign: "center",
        transform: `translateY(-50%) scale(${interpolate(pop, [0, 1], [0.85, 1])})`,
        fontFamily: font,
        fontWeight: 700,
        fontSize: size,
        lineHeight: 1.12,
        textShadow: `${outline(INK, size * 0.09)}, 0 ${size * 0.08}px ${size * 0.14}px rgba(0,0,0,0.45)`,
      }}
    >
      {active.words.map((w, i) => (
        <span key={`${w.start}-${i}`} style={{ color: i === current ? HIGHLIGHT : "#FFFFFF" }}>
          {i > 0 ? " " : ""}
          {w.text}
        </span>
      ))}
    </div>
  );
};

export const Subtitles: React.FC<{ cues: SubtitleCue[]; font: string }> = ({ cues, font }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const time = frame / fps;

  const blocks = React.useMemo(() => groupCues(cues), [cues]);
  if (isVertical(width, height)) {
    return <VerticalSubtitles cues={cues} font={font} />;
  }
  const active = blocks.find((b) => time >= b.start && time <= b.end);
  if (!active) return null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: height * 0.08,
        width: "100%",
        textAlign: "center",
        padding: "0 12%",
      }}
    >
      <span
        style={{
          fontFamily: "Inter, system-ui, sans-serif",
          fontSize: height * 0.045,
          fontWeight: 600,
          color: "#FFFFFF",
          background: "rgba(34, 32, 29, 0.72)",
          padding: "0.35em 0.7em",
          borderRadius: "0.25em",
          lineHeight: 1.35,
          boxDecorationBreak: "clone",
          WebkitBoxDecorationBreak: "clone",
        }}
      >
        {active.text}
      </span>
    </div>
  );
};
