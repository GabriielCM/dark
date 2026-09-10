import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { SubtitleCue } from "../types";

/**
 * Legenda embutida, agrupada em blocos legiveis a partir das palavras.
 *
 * O SRT separado continua sendo a entrega principal (brief 6.3); isto e para
 * quando se quiser queimar a legenda no video.
 */

const MAX_CHARS = 42;

type Block = { start: number; end: number; text: string };

const groupCues = (cues: SubtitleCue[]): Block[] => {
  const blocks: Block[] = [];
  let current: SubtitleCue[] = [];

  const flush = () => {
    if (current.length === 0) return;
    blocks.push({
      start: current[0].start,
      end: current[current.length - 1].end,
      text: current.map((c) => c.text).join(" "),
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

export const Subtitles: React.FC<{ cues: SubtitleCue[] }> = ({ cues }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const time = frame / fps;

  const blocks = React.useMemo(() => groupCues(cues), [cues]);
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
