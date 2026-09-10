"""Contrato do alinhador: audio + texto -> timestamps por palavra."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WordTiming:
    word: str
    start: float
    end: float


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    words: tuple[WordTiming, ...]
    duration_s: float
    provider: str
    model: str

    def to_srt(self, *, max_chars: int = 84, max_seconds: float = 6.0) -> str:
        """Agrupa palavras em legendas legiveis e devolve um SRT.

        Duas linhas de ~42 caracteres e o limite confortavel de leitura em 16:9.
        """
        blocks: list[list[WordTiming]] = []
        current: list[WordTiming] = []

        for word in self.words:
            if current:
                text_len = sum(len(w.word) + 1 for w in current) + len(word.word)
                span = word.end - current[0].start
                ends_sentence = current[-1].word.endswith((".", "!", "?"))
                if text_len > max_chars or span > max_seconds or ends_sentence:
                    blocks.append(current)
                    current = []
            current.append(word)
        if current:
            blocks.append(current)

        lines: list[str] = []
        for index, block in enumerate(blocks, start=1):
            text = " ".join(w.word for w in block).strip()
            lines.append(str(index))
            lines.append(f"{_srt_time(block[0].start)} --> {_srt_time(block[-1].end)}")
            lines.append(_wrap_two_lines(text, max_chars // 2))
            lines.append("")
        return "\n".join(lines)


def _srt_time(seconds: float) -> str:
    total_ms = round(max(0.0, seconds) * 1000)
    hours, rest = divmod(total_ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _wrap_two_lines(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    words = text.split()
    first: list[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > width and first:
            break
        first.append(word)
        length += len(word) + 1
    second = words[len(first) :]
    return "\n".join(filter(None, [" ".join(first), " ".join(second)]))


class AlignProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def align(
        self,
        audio: Path,
        transcript: str,
        *,
        language: str,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> AlignmentResult: ...
