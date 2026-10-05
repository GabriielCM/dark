"""Fixtures compartilhadas.

Cada teste roda num diretorio proprio: banco, videos e livros isolados. Nenhum
teste toca a rede — os adaptadores falsos cobrem todos os provedores.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Aponta todos os caminhos do projeto para um diretorio temporario."""
    monkeypatch.setenv("MA_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("MA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MA_VIDEOS_DIR", str(tmp_path / "videos"))
    monkeypatch.setenv("MA_BOOKS_DIR", str(tmp_path / "livros"))
    monkeypatch.setenv("MA_LIBRARY_DIR", str(tmp_path / "biblioteca"))
    #  Sem isso, um .env real na maquina do dev vazaria para os testes.
    monkeypatch.delenv("MA_PANEL_AUTH_TOKEN", raising=False)
    #  Nenhum teste mostra um aviso de verdade na tela de quem roda a suite.
    monkeypatch.setenv("MA_NOTIFICACOES", "nenhum")

    from mundoantigo.config import reset_settings_cache
    from mundoantigo.db.session import reset_engine_cache
    from mundoantigo.paths import reset_paths_cache
    from mundoantigo.prompts import reset_prompts_cache

    reset_paths_cache()
    reset_settings_cache()
    reset_engine_cache()
    reset_prompts_cache()

    from mundoantigo.paths import get_paths

    get_paths().ensure()
    yield tmp_path

    reset_paths_cache()
    reset_settings_cache()
    reset_engine_cache()
    reset_prompts_cache()


@pytest.fixture
def settings(tmp_project: Path):
    import dataclasses

    from mundoantigo.config import load_settings

    loaded = load_settings()
    #  O padrao e roteiro vindo da sessao do Claude Code; nos testes, o LLM
    #  falso faz esse papel (modo api). O modo sessao tem testes proprios.
    #  Referencias ranqueadas pelo titulo: carregar o CLIP deixaria a suite lenta.
    #  A grade de imagens aprova sozinha: o portao tem testes proprios
    #  (test_redo_and_gates.py), e os demais percorrem o pipeline inteiro.
    return dataclasses.replace(
        loaded,
        app={
            **loaded.app,
            "roteiro": {"modo": "api"},
            "referencias": {**loaded.app.get("referencias", {}), "ranking": "titulo"},
            "revisao_imagens": {"ativo": False},
        },
    )


@pytest.fixture
def sessions(tmp_project: Path):
    from mundoantigo.db.session import get_sessionmaker, init_db

    init_db()
    return get_sessionmaker()


@pytest.fixture
def prices():
    from mundoantigo.costs import PriceTable

    return PriceTable.from_yaml(REPO_ROOT / "config" / "precos.yaml")


@pytest.fixture
def recorder(settings, prices, sessions):
    from mundoantigo.costs import CostRecorder

    return CostRecorder(settings.budget, prices, sessions)


@pytest.fixture
def providers(settings, recorder):
    from mundoantigo.providers import fake_registry

    return fake_registry(settings, recorder)


@pytest.fixture
def make_video(sessions):
    """Cria uma producao no banco.

    Custos referenciam `videos` por chave estrangeira, e no uso normal a
    producao sempre existe antes de qualquer gasto — os testes de custo
    precisam refletir isso.
    """
    from mundoantigo.db.models import Video

    def _make(video_id: str, topic: str = "Tema de teste") -> str:
        with sessions() as s:
            if s.get(Video, video_id) is None:
                s.add(Video(id=video_id, topic=topic))
                s.commit()
        return video_id

    return _make


@pytest.fixture
def sem_remotion(monkeypatch: pytest.MonkeyPatch):
    """Finge que o projeto Remotion nao esta instalado.

    Sem isto, os testes mudam de comportamento conforme alguem tenha rodado
    `npm ci` ou nao: numa maquina com o Node instalado eles renderizariam
    videos de 1080p de verdade. O caminho de render real tem teste proprio,
    marcado `slow`.
    """
    from mundoantigo.render.remotion import RemotionRenderer

    monkeypatch.setattr(
        RemotionRenderer,
        "is_available",
        lambda self: (False, "dependencias nao instaladas: rode `npm ci` em render/"),
    )


@pytest.fixture
def com_remotion(monkeypatch: pytest.MonkeyPatch):
    """Finge um Remotion disponivel que grava um MP4 de mentira.

    Exercita a etapa de montagem inteira — props, sidecars, avanco da fila —
    sem os minutos de render que o teste real custa.
    """
    from mundoantigo.render.remotion import RemotionRenderer, RenderResult

    monkeypatch.setattr(RemotionRenderer, "is_available", lambda self: (True, ""))

    async def falso_render(
        self, props, props_file, output, *, composition="Video", public_dir=None
    ):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 4096)
        return RenderResult(output=output, duration_s=0.0, props_file=props_file)

    monkeypatch.setattr(RemotionRenderer, "render", falso_render)
