"""Base das etapas.

O contrato do ADR 0002: uma etapa declara o que produz (`outputs`) e como
produz (`run`). O runner usa `outputs` para pular etapas ja concluidas sem
gastar, o que e o mecanismo inteiro da retomada.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..context import StepContext, StepResult
from ..state import StepName, StepSpec, spec


class Step(ABC):
    """Uma etapa do pipeline."""

    name: StepName

    @property
    def spec(self) -> StepSpec:
        return spec(self.name)

    @abstractmethod
    def outputs(self, ctx: StepContext) -> list[Path]:
        """Arquivos que esta etapa produz quando termina.

        Declarar de menos faz a etapa ser refeita a toa; declarar de mais faz
        o runner pular uma etapa que nao terminou. Ha teste para os dois casos.
        """

    @abstractmethod
    async def run(self, ctx: StepContext) -> StepResult:
        """Executa a etapa. So e chamada se `outputs` ainda nao esta completa."""

    def is_satisfied(self, ctx: StepContext) -> bool:
        """A etapa ja esta feita? Verificado antes de qualquer gasto."""
        outputs = self.outputs(ctx)
        return bool(outputs) and ctx.store.all_complete(outputs)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} {self.name.value}>"
