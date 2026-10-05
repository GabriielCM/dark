"""Configuracao: YAML para o que e versionado, .env para o que e segredo.

Regra do CLAUDE.md: segredo nunca em YAML, YAML nunca em codigo. Este modulo e
o unico ponto onde os dois se encontram.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError
from .paths import get_paths


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"arquivo de configuracao ausente: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"configuracao invalida (esperava mapa): {path}")
    return data


def _load_dotenv(path: Path) -> None:
    """Le um .env simples para os.environ sem sobrescrever o que ja existe.

    Deliberadamente minimo: sem interpolacao, sem multilinha. Um .env que
    precisa dessas coisas e um .env que devia ser outra coisa.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve ser numero, veio {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} deve ser inteiro, veio {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class BudgetConfig:
    soft_limit_usd: float
    hard_limit_usd: float
    per_video_limit_usd: float
    unknown_model: str  # "strict" | "allow"

    @property
    def strict_unknown_model(self) -> bool:
        return self.unknown_model == "strict"


@dataclass(frozen=True, slots=True)
class QueueConfig:
    max_attempts: int
    lease_minutes: int
    backoff_seconds: tuple[int, ...]
    max_concurrent_videos: int
    gpu_slots: int


@dataclass(frozen=True, slots=True)
class FactsConfig:
    blocks_on: tuple[str, ...]
    max_rewrites: int
    sources_for_high: int


@dataclass(frozen=True, slots=True)
class ScenesConfig:
    seconds_min: float
    seconds_max: float
    seconds_target: float
    #  Frase acima disto (em PT ou no EN) pode ser cortada numa virgula.
    comma_above_s: float
    target_min_s: int
    target_max_s: int


@dataclass(frozen=True, slots=True)
class RenderConfig:
    fps: int
    width: int
    height: int
    project: str
    concurrency: int
    crf: int
    #  Fonte das camadas graficas (render/src/fonts.ts).
    font_family: str = "Comic Neue"


@dataclass(frozen=True, slots=True)
class BackupConfig:
    """Backup local (ADR 0009). Sem destino, o backup fica desligado."""

    destination: str | None = None
    extras: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PanelConfig:
    host: str
    port: int
    auth_token: str | None

    @property
    def is_local_only(self) -> bool:
        return self.host in {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True, slots=True)
class ChannelConfig:
    """Um canal do YouTube: idioma, voz, ritmo, unidades."""

    id: str
    name: str
    language: str
    locale: str
    voice: dict[str, Any]
    narrative: dict[str, Any]
    units: dict[str, Any]
    publishing: dict[str, Any]

    @property
    def wpm(self) -> int:
        return int(self.narrative.get("ppm", 150))

    @property
    def target_min_minutes(self) -> int:
        return int(self.narrative.get("duracao_alvo_min", 12))

    @property
    def target_max_minutes(self) -> int:
        return int(self.narrative.get("duracao_alvo_max", 15))

    @property
    def discloses_synthetic(self) -> bool:
        return bool(self.publishing.get("divulgar_conteudo_sintetico", True))

    @classmethod
    def from_yaml(cls, path: Path) -> ChannelConfig:
        raw = _load_yaml(path)
        try:
            return cls(
                id=raw["id"],
                name=raw["nome"],
                language=raw["idioma"],
                locale=raw.get("locale", raw["idioma"].replace("-", "_")),
                voice=raw.get("voz", {}),
                narrative=raw.get("narrativa", {}),
                units=raw.get("unidades", {}),
                publishing=raw.get("publicacao", {}),
            )
        except KeyError as exc:
            raise ConfigError(f"canal {path.name} sem campo obrigatorio {exc}") from exc


@dataclass(frozen=True, slots=True)
class StyleGuide:
    """Guia de estilo visual. Provisorio ate o teste de estilo (brief 5.1)."""

    id: str
    status: str
    base_prompt: str
    negatives: tuple[str, ...]
    #  As restricoes escritas no prompt positivo (modelos com CFG 1, ADR 0005).
    positive_restrictions: str
    banned_terms: tuple[str, ...]
    palette: dict[str, str]
    camera: dict[str, Any]
    character: dict[str, Any]
    #  Composicao da cena quando o MC recortado cobre um dos lados.
    host_composition: str = ""
    #  Frase que leva a epoca e o lugar do video as imagens, e os tipos de
    #  cena que a recebem (as de gente e lugar).
    setting_template: str = ""
    setting_kinds: tuple[str, ...] = ()

    @classmethod
    def from_yaml(cls, path: Path) -> StyleGuide:
        raw = _load_yaml(path)
        restrictions = raw.get("restricoes", {})
        return cls(
            id=raw.get("id", "sem-id"),
            status=raw.get("status", "provisorio"),
            base_prompt=raw.get("prompt_base", "").strip(),
            negatives=tuple(restrictions.get("negativos", ())),
            positive_restrictions=" ".join(
                str(restrictions.get("negativos_como_positivo", "")).split()
            ),
            banned_terms=tuple(t.lower() for t in restrictions.get("termos_proibidos", ())),
            palette=raw.get("paleta", {}),
            camera=raw.get("camera", {}),
            character=raw.get("personagem", {}),
            host_composition=" ".join(str((raw.get("composicao") or {}).get("com_mc", "")).split()),
            setting_template=" ".join(
                str((raw.get("composicao") or {}).get("ambientacao", "")).split()
            ),
            setting_kinds=tuple(
                str(k) for k in (raw.get("composicao") or {}).get("ambientacao_tipos", ())
            ),
        )

    def setting_for(self, setting: str | None) -> str:
        """A epoca e o lugar do video na frase do guia de estilo; vazio sem eles."""
        if not setting or not self.setting_template:
            return ""
        return self.setting_template.format(ambientacao=" ".join(setting.split()).rstrip("."))

    def composition_for_host(self, side: str) -> str:
        """O lado do MC fica vazio e o assunto vai para os outros dois tercos."""
        if not self.host_composition:
            return ""
        host = "left" if side == "esquerda" else "right"
        free = "right" if host == "left" else "left"
        return self.host_composition.format(mc=host, livre=free)

    def check_originality(self, prompt: str) -> list[str]:
        """Termos proibidos encontrados no prompt.

        Regra do CLAUDE.md: nao gerar conteudo que imite personagens, marcas ou
        estilos de estudios e artistas existentes. Lista vazia significa limpo.
        """
        low = prompt.lower()
        return [term for term in self.banned_terms if term in low]


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuracao completa, montada uma vez por processo."""

    budget: BudgetConfig
    queue: QueueConfig
    facts: FactsConfig
    scenes: ScenesConfig
    render: RenderConfig
    panel: PanelConfig
    providers: dict[str, Any]
    channels: dict[str, ChannelConfig] = field(default_factory=dict)
    _style: StyleGuide | None = None
    backup: BackupConfig = field(default_factory=BackupConfig)
    #  O app.yaml inteiro, para blocos que so uma etapa le (revisao_imagens,
    #  referencias, trilha...). Os blocos com regra propria tem dataclass acima.
    app: dict[str, Any] = field(default_factory=dict)

    @property
    def style(self) -> StyleGuide:
        if self._style is None:  # pragma: no cover - defensivo
            raise ConfigError("guia de estilo nao carregado")
        return self._style

    def channel(self, channel_id: str) -> ChannelConfig:
        try:
            return self.channels[channel_id]
        except KeyError as exc:
            known = ", ".join(sorted(self.channels)) or "nenhum"
            raise ConfigError(
                f"canal desconhecido: {channel_id!r} (configurados: {known})"
            ) from exc

    def provider_config(self, kind: str, name: str | None = None) -> tuple[str, dict[str, Any]]:
        """Devolve (nome do provedor, config dele) para um tipo de provedor.

        `name=None` usa o padrao do YAML. E aqui que "trocar de provedor e
        trocar a configuracao" (CLAUDE.md) vira verdade.
        """
        block = self.providers.get(kind)
        if not isinstance(block, dict):
            raise ConfigError(f"tipo de provedor desconhecido: {kind!r}")
        chosen = name or block.get("padrao")
        if not chosen:
            raise ConfigError(f"provedor {kind!r} sem padrao definido")
        cfg = block.get(chosen)
        if cfg is None:
            raise ConfigError(f"provedor {kind}.{chosen} sem bloco de configuracao")
        return str(chosen), dict(cfg)


def _load_channels(config_dir: Path) -> dict[str, ChannelConfig]:
    channels_dir = config_dir / "canais"
    if not channels_dir.is_dir():
        raise ConfigError(f"diretorio de canais ausente: {channels_dir}")
    channels: dict[str, ChannelConfig] = {}
    for path in sorted(channels_dir.glob("*.yaml")):
        channel = ChannelConfig.from_yaml(path)
        channels[channel.id] = channel
    if not channels:
        raise ConfigError(f"nenhum canal configurado em {channels_dir}")
    return channels


def load_settings(config_dir: Path | None = None) -> Settings:
    paths = get_paths()
    cfg_dir = config_dir or paths.config
    _load_dotenv(paths.root / ".env")

    app = _load_yaml(cfg_dir / "app.yaml")
    budget_raw = app.get("orcamento", {})
    queue_raw = app.get("fila", {})
    facts_raw = app.get("fatos", {})
    scenes_raw = app.get("cenas", {})
    render_raw = app.get("render", {})

    budget = BudgetConfig(
        # O .env vence o YAML: e assim que se aperta o teto sem editar o repositorio.
        soft_limit_usd=_env_float(
            "MA_BUDGET_SOFT_LIMIT_USD", float(budget_raw.get("soft_limit_usd", 35.0))
        ),
        hard_limit_usd=_env_float(
            "MA_BUDGET_HARD_LIMIT_USD", float(budget_raw.get("hard_limit_usd", 50.0))
        ),
        per_video_limit_usd=_env_float(
            "MA_BUDGET_PER_VIDEO_LIMIT_USD", float(budget_raw.get("per_video_limit_usd", 5.0))
        ),
        unknown_model=str(budget_raw.get("modelo_desconhecido", "strict")),
    )
    if budget.soft_limit_usd > budget.hard_limit_usd:
        raise ConfigError(
            f"teto soft (US$ {budget.soft_limit_usd}) acima do hard "
            f"(US$ {budget.hard_limit_usd}) — o aviso nunca dispararia"
        )

    queue = QueueConfig(
        max_attempts=int(queue_raw.get("max_attempts", 3)),
        lease_minutes=int(queue_raw.get("lease_minutes", 30)),
        backoff_seconds=tuple(int(s) for s in queue_raw.get("backoff_seconds", (30, 120, 480))),
        max_concurrent_videos=int(queue_raw.get("max_videos_concorrentes", 1)),
        gpu_slots=int(queue_raw.get("gpu_slots", 1)),
    )

    facts = FactsConfig(
        blocks_on=tuple(facts_raw.get("bloqueia_em", ("baixa",))),
        max_rewrites=int(facts_raw.get("max_reescritas", 2)),
        sources_for_high=int(facts_raw.get("fontes_para_alta", 2)),
    )

    scenes = ScenesConfig(
        seconds_min=float(scenes_raw.get("segundos_por_cena_min", 4.0)),
        seconds_max=float(scenes_raw.get("segundos_por_cena_max", 8.0)),
        seconds_target=float(scenes_raw.get("segundos_por_cena_alvo", 6.0)),
        comma_above_s=float(scenes_raw.get("corte_em_virgula_acima_s", 8.0)),
        target_min_s=int(scenes_raw.get("duracao_alvo_min_s", 720)),
        target_max_s=int(scenes_raw.get("duracao_alvo_max_s", 900)),
    )

    render = RenderConfig(
        fps=int(render_raw.get("fps", 30)),
        width=int(render_raw.get("largura", 1920)),
        height=int(render_raw.get("altura", 1080)),
        project=str(render_raw.get("projeto", "render")),
        concurrency=int(render_raw.get("concurrency", 2)),
        crf=int(render_raw.get("crf", 18)),
        font_family=str(render_raw.get("fonte", "Comic Neue")),
    )

    token = os.environ.get("MA_PANEL_AUTH_TOKEN") or None
    panel = PanelConfig(
        host=os.environ.get("MA_PANEL_HOST", "127.0.0.1"),
        port=_env_int("MA_PANEL_PORT", 8765),
        auth_token=token,
    )
    if not panel.is_local_only and not panel.auth_token:
        # CLAUDE.md, Seguranca: painel fora da rede local exige autenticacao.
        raise ConfigError(
            f"painel exposto em {panel.host} sem MA_PANEL_AUTH_TOKEN. "
            "Fora de 127.0.0.1 a autenticacao e obrigatoria."
        )

    backup_raw = app.get("backup", {})
    backup = BackupConfig(
        destination=os.environ.get("MA_BACKUP_DESTINO") or backup_raw.get("destino") or None,
        extras=tuple(str(p) for p in backup_raw.get("extras", ())),
    )

    return Settings(
        budget=budget,
        queue=queue,
        facts=facts,
        scenes=scenes,
        render=render,
        panel=panel,
        providers=app.get("provedores", {}),
        channels=_load_channels(cfg_dir),
        _style=StyleGuide.from_yaml(cfg_dir / "estilo" / "guia.yaml"),
        backup=backup,
        app=app,
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
