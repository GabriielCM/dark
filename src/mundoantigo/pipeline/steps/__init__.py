"""As dezesseis etapas do pipeline, na ordem de pipeline/state.py."""

from __future__ import annotations

from ..state import StepName
from .base import Step
from .s01_pauta import PautaStep
from .s02_pesquisa import PesquisaStep
from .s03_roteiro import RoteiroStep
from .s04_gate_fatos import GateFatosStep
from .s05_adaptacao_en import AdaptacaoEnStep
from .s06_narracao import NarracaoStep
from .s07_cenas import CenasStep
from .s08_referencias import ReferenciasStep
from .s09_assets import AssetsStep
from .s10_pre_checagem import PreChecagemStep
from .s11_revisao_imagens import RevisaoImagensStep
from .s12_trilha import TrilhaStep
from .s13_metadados import MetadadosStep
from .s14_montagem import MontagemStep
from .s15_revisao import RevisaoStep
from .s16_entrega import EntregaStep

ALL_STEPS: tuple[type[Step], ...] = (
    PautaStep,
    PesquisaStep,
    RoteiroStep,
    GateFatosStep,
    AdaptacaoEnStep,
    NarracaoStep,
    CenasStep,
    ReferenciasStep,
    AssetsStep,
    PreChecagemStep,
    RevisaoImagensStep,
    TrilhaStep,
    MetadadosStep,
    MontagemStep,
    RevisaoStep,
    EntregaStep,
)

STEP_BY_NAME: dict[StepName, type[Step]] = {cls.name: cls for cls in ALL_STEPS}


def build(name: StepName | str) -> Step:
    key = StepName(name) if isinstance(name, str) else name
    return STEP_BY_NAME[key]()


__all__ = ["ALL_STEPS", "STEP_BY_NAME", "Step", "build"]
