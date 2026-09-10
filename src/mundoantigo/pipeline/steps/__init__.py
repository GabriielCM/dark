"""As doze etapas do pipeline, na ordem do CLAUDE.md."""

from __future__ import annotations

from ..state import StepName
from .base import Step
from .s01_pauta import PautaStep
from .s02_pesquisa import PesquisaStep
from .s03_roteiro import RoteiroStep
from .s04_gate_fatos import GateFatosStep
from .s05_adaptacao_en import AdaptacaoEnStep
from .s06_cenas import CenasStep
from .s07_assets import AssetsStep
from .s08_narracao import NarracaoStep
from .s09_montagem import MontagemStep
from .s10_metadados import MetadadosStep
from .s11_revisao import RevisaoStep
from .s12_entrega import EntregaStep

ALL_STEPS: tuple[type[Step], ...] = (
    PautaStep,
    PesquisaStep,
    RoteiroStep,
    GateFatosStep,
    AdaptacaoEnStep,
    CenasStep,
    AssetsStep,
    NarracaoStep,
    MontagemStep,
    MetadadosStep,
    RevisaoStep,
    EntregaStep,
)

STEP_BY_NAME: dict[StepName, type[Step]] = {cls.name: cls for cls in ALL_STEPS}


def build(name: StepName | str) -> Step:
    key = StepName(name) if isinstance(name, str) else name
    return STEP_BY_NAME[key]()


__all__ = ["ALL_STEPS", "STEP_BY_NAME", "Step", "build"]
