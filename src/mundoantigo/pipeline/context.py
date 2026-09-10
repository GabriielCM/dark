"""Contexto entregue a cada etapa.

Reune tudo que uma etapa precisa e nada que ela nao precise: sem acesso direto
a sessao do banco, por exemplo — quem persiste estado da fila e o runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..artifacts import ArtifactStore
from ..config import ChannelConfig, Settings
from ..costs import CostRecorder
from ..prompts import PromptRegistry
from ..providers import ProviderRegistry


@dataclass(slots=True)
class StepContext:
    video_id: str
    topic: str
    pillar: str
    settings: Settings
    providers: ProviderRegistry
    prompts: PromptRegistry
    costs: CostRecorder
    store: ArtifactStore
    step_run_id: int | None = None
    #  Livro de origem, quando a pauta vem de um capitulo (brief 4.1).
    book_id: str | None = None
    book_chapter: int | None = None
    #  Espaco para uma etapa deixar recado para a proxima dentro da mesma rodada.
    scratch: dict[str, Any] = field(default_factory=dict)

    @property
    def channel_pt(self) -> ChannelConfig:
        return self.settings.channel("pt-br")

    @property
    def channel_en(self) -> ChannelConfig:
        return self.settings.channel("en")

    def channels(self) -> tuple[ChannelConfig, ChannelConfig]:
        """Os dois canais, na ordem em que o pipeline os trata."""
        return self.channel_pt, self.channel_en


@dataclass(slots=True)
class StepResult:
    """O que uma etapa devolve ao runner."""

    ok: bool = True
    #  Resumo curto para o painel.
    summary: str = ""
    #  Dados estruturados guardados em `steps.result`.
    data: dict[str, Any] = field(default_factory=dict)
    #  Etapa pediu humano: vira `blocked`, nao `failed`.
    needs_human: bool = False
    blocked_reason: str | None = None

    @classmethod
    def done(cls, summary: str = "", **data: Any) -> StepResult:
        return cls(ok=True, summary=summary, data=data)

    @classmethod
    def blocked(cls, reason: str, **data: Any) -> StepResult:
        return cls(ok=False, needs_human=True, blocked_reason=reason, summary=reason, data=data)
