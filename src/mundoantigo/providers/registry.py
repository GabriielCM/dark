"""Registro de provedores.

Este modulo e onde "trocar de provedor deve ser so trocar a configuracao"
(CLAUDE.md) para de ser promessa e vira mecanismo: o resto do codigo pede
`providers.llm()` e nunca sabe qual implementacao recebeu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..costs import CostRecorder
from ..errors import ConfigError
from .align import AlignProvider, FakeAlign, FasterWhisperAlign
from .image import ComfyUIImage, FakeImage, FluxLocal, ImageProvider, OpenRouterImage
from .llm import FakeLLM, LLMProvider, OpenRouterLLM
from .llm.demo import demo_responder
from .search import BraveSearch, FakeSearch, SearchProvider
from .tts import ElevenLabsTTS, FakeTTS, FishAudioTTS, GeminiTTS, KokoroTTS, TTSProvider

#  kind -> nome no YAML -> classe.
_IMPLEMENTATIONS: dict[str, dict[str, type[Any]]] = {
    "llm": {"openrouter": OpenRouterLLM, "fake": FakeLLM},
    "imagem": {
        "comfyui": ComfyUIImage,
        "flux_local": FluxLocal,
        "openrouter": OpenRouterImage,
        "fake": FakeImage,
    },
    "tts": {
        "kokoro": KokoroTTS,
        "elevenlabs": ElevenLabsTTS,
        "fish": FishAudioTTS,
        "gemini": GeminiTTS,
        "fake": FakeTTS,
    },
    "alinhamento": {"faster_whisper": FasterWhisperAlign, "fake": FakeAlign},
    "busca": {"brave": BraveSearch, "fake": FakeSearch},
}


@dataclass
class ProviderRegistry:
    """Fabrica de adaptadores, resolvida a partir da configuracao."""

    settings: Settings
    costs: CostRecorder
    #  Sobrescritas explicitas, usadas por testes e pelo modo de ensaio.
    overrides: dict[str, Any] | None = None

    def _build(self, kind: str, name: str | None, model_key: str | None = None) -> Any:
        if self.overrides and kind in self.overrides:
            return self.overrides[kind]

        chosen, cfg = self.settings.provider_config(kind, name)
        impls = _IMPLEMENTATIONS.get(kind, {})
        cls = impls.get(chosen)
        if cls is None:
            known = ", ".join(sorted(impls)) or "nenhum"
            raise ConfigError(f"provedor {kind}.{chosen!r} sem implementacao (conhecidos: {known})")

        model = cfg.get(model_key) if model_key else cfg.get("modelo")
        kwargs: dict[str, Any] = {"costs": self.costs, "config": cfg}
        if model:
            kwargs["model"] = str(model)
        return cls(**kwargs)

    # -- acessores tipados -------------------------------------------------

    def llm(self, *, fast: bool = False, name: str | None = None) -> LLMProvider:
        """Provedor de texto.

        `fast=True` pede o modelo barato — storyboard, tags, coisas mecanicas.
        O padrao e o modelo bom, usado em roteiro e checagem de fatos.
        """
        key = "modelo_rapido" if fast else "modelo_principal"
        return self._build("llm", name, model_key=key)

    def image(self, *, name: str | None = None) -> ImageProvider:
        return self._build("imagem", name)

    def tts(self, *, name: str | None = None) -> TTSProvider:
        return self._build("tts", name)

    def align(self, *, name: str | None = None) -> AlignProvider:
        return self._build("alinhamento", name)

    def search(self, *, name: str | None = None) -> SearchProvider:
        return self._build("busca", name)

    def describe(self) -> dict[str, str]:
        """Quem esta configurado agora. Vai para o painel e para os sidecars."""
        out: dict[str, str] = {}
        for kind in _IMPLEMENTATIONS:
            try:
                chosen, cfg = self.settings.provider_config(kind)
                model = cfg.get("modelo") or cfg.get("modelo_principal") or "-"
                out[kind] = f"{chosen} ({model})"
            except ConfigError:
                out[kind] = "nao configurado"
        return out


def fake_registry(settings: Settings, costs: CostRecorder, **fakes: Any) -> ProviderRegistry:
    """Registro com todos os provedores falsos, para testes e para o `--ensaio`.

    O LLM padrao usa as respostas de ensaio (`demo_responder`), coerentes entre
    as etapas: sem isso o gate de fatos bloquearia num relatorio vazio e o
    ensaio nunca chegaria a montagem.
    """
    overrides: dict[str, Any] = {
        "llm": fakes.get("llm") or FakeLLM(costs=costs, responses=demo_responder()),
        "imagem": fakes.get("imagem") or FakeImage(costs=costs),
        "tts": fakes.get("tts") or FakeTTS(costs=costs),
        "alinhamento": fakes.get("alinhamento") or FakeAlign(costs=costs),
        "busca": fakes.get("busca") or FakeSearch(costs=costs),
    }
    return ProviderRegistry(settings=settings, costs=costs, overrides=overrides)
