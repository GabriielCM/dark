"""Maquina de estados de uma producao.

As dezesseis etapas, na ordem, com as dependencias explicitas. Este modulo nao
executa nada: ele so responde "o que vem depois" e "isso pode rodar".

Ha duas revisoes humanas (brief 3.5, revisto em 09/2026): a grade de imagens
(`revisao_imagens`) e o corte final (`revisao`). A narracao depende so da
adaptacao EN, nao das imagens: voz e trilha rodam enquanto a grade espera.
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
    REFERENCIAS = "referencias"
    ASSETS = "assets"
    PRE_CHECAGEM = "pre_checagem"
    REVISAO_IMAGENS = "revisao_imagens"
    NARRACAO = "narracao"
    TRILHA = "trilha"
    METADADOS = "metadados"
    MONTAGEM = "montagem"
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


S = StepName

PIPELINE: tuple[StepSpec, ...] = (
    StepSpec(S.PAUTA, 1, ()),
    StepSpec(S.PESQUISA, 2, (S.PAUTA,), can_spend=True),
    StepSpec(S.ROTEIRO, 3, (S.PESQUISA,), can_spend=True),
    #  O gate roda o relatorio de fatos e tenta reescrever antes de escalar.
    StepSpec(S.GATE_FATOS, 4, (S.ROTEIRO,), can_spend=True, human_gate=True),
    StepSpec(S.ADAPTACAO_EN, 5, (S.GATE_FATOS,), can_spend=True),
    StepSpec(S.CENAS, 6, (S.ADAPTACAO_EN,), can_spend=True),
    StepSpec(S.REFERENCIAS, 7, (S.CENAS,)),
    StepSpec(S.ASSETS, 8, (S.REFERENCIAS,), gpu_bound=True, can_spend=True),
    #  A pre-checagem para quando sobram suspeitas para o Claude revisar.
    StepSpec(S.PRE_CHECAGEM, 9, (S.ASSETS,), gpu_bound=True, human_gate=True),
    StepSpec(S.REVISAO_IMAGENS, 10, (S.PRE_CHECAGEM,), human_gate=True),
    StepSpec(S.NARRACAO, 11, (S.ADAPTACAO_EN,), gpu_bound=True, can_spend=True),
    StepSpec(S.TRILHA, 12, (S.NARRACAO,)),
    #  Metadados antes do render: um erro neles aparece antes de uma hora de render.
    StepSpec(S.METADADOS, 13, (S.REVISAO_IMAGENS, S.TRILHA), can_spend=True),
    StepSpec(S.MONTAGEM, 14, (S.REVISAO_IMAGENS, S.TRILHA), gpu_bound=True),
    StepSpec(S.REVISAO, 15, (S.MONTAGEM, S.METADADOS), human_gate=True),
    StepSpec(S.ENTREGA, 16, (S.REVISAO,)),
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

    Depois da adaptacao EN o pipeline se divide em dois ramos: imagens
    (referencias, assets, pre-checagem, revisao) e audio (narracao, trilha).
    Eles voltam a se juntar em metadados e montagem.
    """
    return [s.name for s in PIPELINE if s.name not in done and dependencies_met(s.name, done)]


def downstream(targets: set[StepName] | list[StepName]) -> list[StepName]:
    """As etapas alvo e todas que dependem delas, direta ou indiretamente.

    E o conjunto que precisa ser refeito quando um alvo e refeito: refazer a
    narracao invalida trilha, metadados, montagem, revisao e entrega, mas nao
    as imagens.
    """
    affected = set(targets)
    for step in PIPELINE:  # PIPELINE ja esta em ordem topologica
        if any(dep in affected for dep in step.depends_on):
            affected.add(step.name)
    return [s.name for s in PIPELINE if s.name in affected]
