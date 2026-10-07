"""Configuracao e prompts.

Segredo nunca em YAML, YAML nunca em codigo, prompt sempre em arquivo
(CLAUDE.md, convencoes).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from mundoantigo.config import StyleGuide, load_settings
from mundoantigo.errors import ConfigError
from mundoantigo.prompts import PromptRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSettings:
    def test_both_channels_are_configured(self, settings) -> None:
        assert set(settings.channels) == {"pt-br", "en"}
        assert settings.channel("pt-br").language == "pt-BR"
        assert settings.channel("en").language == "en-US"

    def test_unknown_channel_names_the_known_ones(self, settings) -> None:
        with pytest.raises(ConfigError, match="pt-br"):
            settings.channel("fr")

    def test_english_channel_adapts_not_translates(self, settings) -> None:
        assert settings.channel("en").narrative["origem"] == "adaptacao_de_pt_br"

    def test_env_overrides_yaml_budget(self, tmp_project, monkeypatch) -> None:
        """O .env vence o YAML: aperta-se o teto sem editar o repositorio."""
        monkeypatch.setenv("MA_BUDGET_HARD_LIMIT_USD", "12.5")
        monkeypatch.setenv("MA_BUDGET_SOFT_LIMIT_USD", "8")
        from mundoantigo.config import reset_settings_cache

        reset_settings_cache()
        budget = load_settings().budget
        assert budget.hard_limit_usd == 12.5
        assert budget.soft_limit_usd == 8.0

    def test_soft_above_hard_is_refused(self, tmp_project, monkeypatch) -> None:
        """Aviso acima do teto nunca dispararia — e erro de configuracao."""
        monkeypatch.setenv("MA_BUDGET_SOFT_LIMIT_USD", "80")
        monkeypatch.setenv("MA_BUDGET_HARD_LIMIT_USD", "50")
        from mundoantigo.config import reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ConfigError, match="acima do hard"):
            load_settings()

    def test_exposed_panel_requires_auth(self, tmp_project, monkeypatch) -> None:
        """CLAUDE.md, Seguranca: fora da rede local, autenticacao e obrigatoria."""
        monkeypatch.setenv("MA_PANEL_HOST", "0.0.0.0")
        monkeypatch.delenv("MA_PANEL_AUTH_TOKEN", raising=False)
        from mundoantigo.config import reset_settings_cache

        reset_settings_cache()
        with pytest.raises(ConfigError, match="MA_PANEL_AUTH_TOKEN"):
            load_settings()

    def test_exposed_panel_with_token_is_allowed(self, tmp_project, monkeypatch) -> None:
        monkeypatch.setenv("MA_PANEL_HOST", "0.0.0.0")
        monkeypatch.setenv("MA_PANEL_AUTH_TOKEN", "segredo")
        from mundoantigo.config import reset_settings_cache

        reset_settings_cache()
        assert load_settings().panel.auth_token == "segredo"

    def test_scene_pace_is_configurable(self, settings) -> None:
        """Ritmo dos videos entregues: ~6 s por imagem (docs/estilo/analise-entregas.md)."""
        assert settings.scenes.seconds_target == 6.0
        assert settings.scenes.seconds_min == 4.0
        assert settings.scenes.seconds_max == 8.0
        assert settings.scenes.comma_above_s == 8.0

    def test_the_host_side_is_left_free_in_the_scene(self, settings) -> None:
        """O MC recortado cobre um lado: o assunto vai para os outros dois tercos."""
        text = settings.style.composition_for_host("esquerda")
        assert "right two thirds" in text and "left third" in text
        assert "left two thirds" in settings.style.composition_for_host("direita")

    def test_the_setting_reaches_people_and_places_but_not_objects(self, settings) -> None:
        """A epoca e o lugar vao para cenas de gente e lugar, nunca para a peca no branco.

        Sem ela, "workers" e "city" sairam europeus e modernos no video do Egito;
        com ela numa peca, o objeto isolado ganhava gente e predios em volta.
        """
        from types import SimpleNamespace

        from mundoantigo.pipeline.steps.s09_assets import AssetsStep
        from mundoantigo.prompts.registry import get_prompts

        setting = settings.style.setting_for("ancient Egypt, Old Kingdom.")
        assert setting.startswith("Setting: ancient Egypt, Old Kingdom.")
        assert settings.style.setting_for(None) == ""

        ctx = SimpleNamespace(settings=settings, prompts=get_prompts())
        host = {"descricao_fixa": "a friendly man", "figurino": "a linen kilt"}

        def render(kind: str) -> str:
            return AssetsStep._render(None, ctx, kind, "a street", None, host, setting=setting)  # type: ignore[arg-type]

        assert "ancient Egypt" in render("lugar")
        assert "ancient Egypt" in render("atuada")
        assert "ancient Egypt" not in render("peca")
        assert "ancient Egypt" not in render("infografico")

    def test_provider_config_resolves_default(self, settings) -> None:
        name, cfg = settings.provider_config("llm")
        assert name == "openrouter"
        assert "modelo_principal" in cfg


class TestSecretsStayOutOfYaml:
    def test_no_api_keys_in_committed_config(self) -> None:
        """Um segredo em YAML seria commitado. Este teste impede isso.

        Olha chaves e valores do YAML ja interpretado, nao o texto cru: o texto
        cru tem comentarios que falam de `token_io`, que e unidade de preco e
        nao credencial.
        """
        suspeitos = ("api_key", "apikey", "secret", "password", "senha", "credential")

        def varrer(node, caminho: str, arquivo: str) -> None:
            if isinstance(node, dict):
                for chave, valor in node.items():
                    nome = str(chave).lower()
                    assert not any(t in nome for t in suspeitos), (
                        f"{arquivo}: chave {caminho}.{chave} parece credencial"
                    )
                    varrer(valor, f"{caminho}.{chave}", arquivo)
            elif isinstance(node, list):
                for i, item in enumerate(node):
                    varrer(item, f"{caminho}[{i}]", arquivo)
            elif isinstance(node, str):
                assert not node.startswith(("sk-", "sk_", "xi-", "Bearer ")), (
                    f"{arquivo}: valor em {caminho} parece uma chave de API"
                )

        for path in (REPO_ROOT / "config").rglob("*.yaml"):
            varrer(yaml.safe_load(path.read_text(encoding="utf-8")), "", path.name)

    def test_gitignore_covers_env(self) -> None:
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "\n.env\n" in gitignore


class TestStyleGuide:
    def test_originality_check_catches_banned_terms(self, settings) -> None:
        """CLAUDE.md: nao imitar personagens, marcas ou estilos existentes."""
        style = settings.style
        assert style.check_originality("a castle in the style of Studio Ghibli")
        assert style.check_originality("PIXAR style character")  # sem distincao de caixa
        assert not style.check_originality("flat vector illustration of a roman aqueduct")

    def test_negatives_block_explicit_violence(self, settings) -> None:
        """Batalhas sem sangue nem mortes explicitas (brief 3.3)."""
        negativos = set(settings.style.negatives)
        assert {"blood", "gore"} <= negativos

    def test_style_was_approved_in_the_calibration(self, settings) -> None:
        """Estilo aprovado contra o teste de 17/09 (config/estilo/guia.yaml)."""
        assert settings.style.status == "aprovado"
        assert "No text" in settings.style.positive_restrictions
        assert settings.style.character["descricao_fixa"]

    def test_missing_file_fails_clearly(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="ausente"):
            StyleGuide.from_yaml(tmp_path / "nao-existe.yaml")


class TestPrompts:
    def test_all_prompts_load(self, tmp_project) -> None:
        registry = PromptRegistry(REPO_ROOT / "prompts")
        ids = registry.all_ids()
        assert "roteiro/roteiro_ptbr" in ids
        assert "gate/reescrita" in ids
        assert len(ids) >= 8

    def test_prompt_ref_includes_version(self, tmp_project) -> None:
        """O sidecar guarda a versao do prompt (CLAUDE.md, rastreabilidade)."""
        prompt = PromptRegistry(REPO_ROOT / "prompts").get("pesquisa/dossie")
        assert prompt.ref == "pesquisa/dossie@v1"
        assert len(prompt.checksum) == 12

    def test_render_fills_variables(self, tmp_project) -> None:
        prompt = PromptRegistry(REPO_ROOT / "prompts").get("adaptacao/en")
        rendered = prompt.render(
            roteiro_ptbr="ROTEIRO",
            ppm=160,
            duracao_alvo_min=12,
            duracao_alvo_max=15,
            unidades="imperial",
            tom="serious",
            limites_por_bloco="- Block 1: at most 120 words",
        )
        assert "ROTEIRO" in rendered
        assert "{roteiro_ptbr}" not in rendered
        assert "at most 120 words" in rendered

    def test_missing_variable_names_the_declared_ones(self, tmp_project) -> None:
        prompt = PromptRegistry(REPO_ROOT / "prompts").get("adaptacao/en")
        with pytest.raises(ConfigError, match="variavel"):
            prompt.render(roteiro_ptbr="x")

    def test_json_braces_survive_rendering(self, tmp_project) -> None:
        """Todo prompt pede JSON; chaves literais precisam sobreviver ao format."""
        registry = PromptRegistry(REPO_ROOT / "prompts")
        prompt = registry.get("roteiro/relatorio_fatos")
        rendered = prompt.render(roteiro="R", dossie="D")
        assert '"itens"' in rendered
        assert "{{" not in rendered

    def test_every_prompt_declares_its_variables(self) -> None:
        registry = PromptRegistry(REPO_ROOT / "prompts")
        for prompt_id in registry.all_ids():
            prompt = registry.get(prompt_id)
            assert "descricao" in prompt.metadata, f"{prompt_id} sem descricao"
            assert "variaveis" in prompt.metadata, f"{prompt_id} sem variaveis declaradas"

    def test_unknown_prompt_lists_the_known_ones(self, tmp_project) -> None:
        registry = PromptRegistry(REPO_ROOT / "prompts")
        with pytest.raises(ConfigError, match="existentes"):
            registry.get("nao/existe")

    def test_version_mismatch_is_refused(self, tmp_path: Path) -> None:
        """O nome do arquivo e a verdade sobre a versao."""
        (tmp_path / "x.v2.md").write_text("---\nid: x\nversion: 3\n---\ncorpo", encoding="utf-8")
        with pytest.raises(ConfigError, match="difere do nome"):
            PromptRegistry(tmp_path).get("x")

    def test_latest_version_wins(self, tmp_path: Path) -> None:
        for version in (1, 2):
            (tmp_path / f"p.v{version}.md").write_text(
                f"---\nid: p\nversion: {version}\n---\nv{version}", encoding="utf-8"
            )
        assert PromptRegistry(tmp_path).get("p").version == 2
        assert PromptRegistry(tmp_path).get("p", version=1).version == 1


class TestPriceTableFile:
    def test_every_provider_in_app_yaml_has_prices(self) -> None:
        """Adicionar provedor pago exige adicionar preco. Friccao deliberada."""
        app = yaml.safe_load((REPO_ROOT / "config" / "app.yaml").read_text(encoding="utf-8"))
        precos = yaml.safe_load((REPO_ROOT / "config" / "precos.yaml").read_text(encoding="utf-8"))
        modelos_com_preco = {
            m for bloco in precos.values() if isinstance(bloco, dict) for m in bloco
        }
        for tipo, bloco in app["provedores"].items():
            for nome, cfg in bloco.items():
                if nome == "padrao" or not isinstance(cfg, dict):
                    continue
                for chave in ("modelo", "modelo_principal", "modelo_rapido"):
                    modelo = cfg.get(chave)
                    if modelo:
                        assert modelo in modelos_com_preco, (
                            f"{tipo}.{nome}.{chave} = {modelo} nao esta em precos.yaml"
                        )
