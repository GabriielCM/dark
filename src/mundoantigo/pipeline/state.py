"""Maquina de estados de uma producao.

As doze etapas do CLAUDE.md, na ordem, com as dependencias explicitas. Este
modulo nao executa nada: ele so responde "o que vem depois" e "isso pode rodar".
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from ..db.models import VideoState


class StepName(enum.StrEnum):
    PAUTA = "pauta"
    PESQUISA = "pesquisa"
    ROTEIRO = "roteiro"
    GATE_FATOS = "gate_fatos"
    ADAPTACAO_EN = "adaptacao_en"
    CENAS = "cenas"
    ASSETS = "assets"
    NARRACAO = "narracao"
    MONTAGEM = "montagem"
    METADADOS = "metadados"
    REVISAO = "revisao"
    ENTREGA = "entregue"


@dataclass(frozen=True, slots=True)
class StepSpec:
    name: StepName
    ordinal: int
    depends_on: tuple[StepName, ...]
    #  Etapa que disputa a GPU: serializa com as outras marcadas assim.
    gpu_bound: bool = False
    #  Etapa que pode gastar dinheiro. O painel usa isso para avisar.
    can_spend: bool = False
    #  Etapa que espera humano em vez de falhar.
    human_gate: bool = False


PIPELINE: tuple[StepSpec, ...] = (
    StepSpec(StepName.PAUTA, 1, ()),
    StepSpec(StepName.PESQUISA, 2, (StepName.PAUTA,), can_spend=True),
    StepSpec(StepName.ROTEIRO, 3, (StepName.PESQUISA,), can_spend=True),
    #  O gate roda o relatorio de fatos e tenta reescrever antes de escalar.
    StepSpec(StepName.GATE_FATOS, 4, (StepName.ROTEIRO,), can_spend=True, human_gate=True),
    StepSpec(StepName.ADAPTACAO_EN, 5, (StepName.GATE_FATOS,), can_spend=True),
    StepSpec(StepName.CENAS, 6, (StepName.ADAPTACAO_EN,), can_spend=True),
    StepSpec(StepName.ASSETS, 7, (StepName.CENAS,), gpu_bound=True, can_spend=True),
    StepSpec(StepName.NARRACAO, 8, (StepName.CENAS,), gpu_bound=True, can_spend=True),
    StepSpec(StepName.MONTAGEM, 9, (StepName.ASSETS, StepName.NARRACAO), gpu_bound=True),
    StepSpec(StepName.METADADOS, 10, (StepName.MONTAGEM,), can_spend=True),
    StepSpec(StepName.REVISAO, 11, (StepName.METADADOS,), human_gate=True),
    StepSpec(StepName.ENTREGA, 12, (StepName.REVISAO,)),
)

BY_NAME: dict[StepName, StepSpec] = {spec.name: spec for spec in PIPELINE}

#  Cada etapa tem um estado de video correspondente, de mesmo nome — menos a
#  ultima: enquanto o pacote esta sendo montado a producao esta `empacotando`,
#  e so vira `entregue` quando a etapa conclui (ver VideoState.EMPACOTANDO).
STEP_TO_VIDEO_STATE: dict[StepName, VideoState] = {
    **{step: VideoState(step.value) for step in StepName if step is not StepName.ENTREGA},
    StepName.ENTREGA: VideoState.EMPACOTANDO,
}


def spec(name: StepName | str) -> StepSpec:
    key = StepName(name) if isinstance(name, str) else name
    return BY_NAME[key]


def next_step(name: StepName) -> StepName | None:
    ordinal = spec(name).ordinal
    for candidate in PIPELINE:
        if candidate.ordinal == ordinal + 1:
            return candidate.name
    return None


def steps_in_order() -> tuple[StepName, ...]:
    return tuple(s.name for s in PIPELINE)


def dependencies_met(name: StepName, done: set[StepName]) -> bool:
    return all(dep in done for dep in spec(name).depends_on)


def ready_steps(done: set[StepName]) -> list[StepName]:
    """Etapas cujas dependencias ja terminaram e que ainda nao rodaram.

    O pipeline e quase linear, mas `assets` e `narracao` dependem so de `cenas`
    — e essa e a unica bifurcacao real. Ambas disputam a GPU, entao quem
    serializa e o semaforo, nao a ordem.
    """
    return [s.name for s in PIPELINE if s.name not in done and dependencies_met(s.name, done)]
