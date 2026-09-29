"""Contrato do provedor de voz.

O vencedor do teste cego (brief 6.1) entra por configuracao. O adaptador
existe antes da escolha, que e exatamente o que o CLAUDE.md pede.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SpeechRequest:
    text: str
    voice_id: str
    language: str
    speed: float = 1.0
    #  Frase a frase, com a pausa depois de cada uma. Quem suporta (Kokoro)
    #  devolve o tempo exato de cada frase; quem nao suporta sintetiza `text`.
    segments: tuple[str, ...] = ()
    pauses: tuple[float, ...] = ()


@dataclass(frozen=True, slots=True)
class SpeechResult:
    path: Path
    provider: str
    model: str
    voice_id: str
    characters: int
    duration_s: float | None = None
    #  (inicio, fim) de cada segmento, em segundos, quando houve segmentos.
    segment_times: tuple[tuple[float, float], ...] = ()


class TTSProvider(Protocol):
    name: str
    model: str
    is_local: bool

    async def synthesize(
        self,
        request: SpeechRequest,
        destination: Path,
        *,
        step: str,
        video_id: str | None = None,
        step_run_id: int | None = None,
    ) -> SpeechResult: ...
