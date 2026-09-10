"""Render de verdade no Remotion.

Marcado `slow` porque exige `npm ci` em `render/` e sobe um Chromium. Nao roda
no conjunto padrao — `pytest -m slow` para rodar so estes.

Vale o custo: e o unico teste que prova a ponte Python -> Remotion de ponta a
ponta, e a fronteira entre os dois processos e onde as coisas quebram calado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.providers.image.fake import _solid_png
from mundoantigo.providers.tts.fake import _silence_wav
from mundoantigo.render import RemotionRenderer, SceneProps, SubtitleCue, VideoProps

REPO_ROOT = Path(__file__).resolve().parents[1]

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not (REPO_ROOT / "render" / "node_modules").is_dir(),
        reason="rode `npm ci` em render/ para exercitar o render de verdade",
    ),
]


@pytest.fixture
def cena_pronta(settings, tmp_project) -> tuple[ArtifactStore, VideoProps]:
    """Tres cenas de 2 s em resolucao baixa: prova a ponte sem custar minutos."""
    store = ArtifactStore("render-real")
    store.ensure()

    for index in range(1, 4):
        store.path("assets", f"cena-{index:03d}.png").write_bytes(
            _solid_png(640, 360, (40 + index * 60, 90, 140))
        )
    store.path("narracao", "narracao.pt-br.wav").write_bytes(_silence_wav(6.0))

    props = VideoProps(
        videoId="render-real",
        language="pt-BR",
        title="Teste de render",
        fps=30,
        width=640,
        height=360,
        durationInSeconds=6.0,
        narration="narracao/narracao.pt-br.wav",
        scenes=[
            SceneProps(
                index=index,
                background=f"assets/cena-{index:03d}.png",
                start=(index - 1) * 2.0,
                duration=2.0,
                camera=["zoom_in", "pan_left", "estatica"][index - 1],
                layers=["frente", "meio", "fundo"],
            )
            for index in range(1, 4)
        ],
        palette=settings.style.palette,
    )
    return store, props


async def test_renders_a_playable_mp4(settings, cena_pronta) -> None:
    store, props = cena_pronta
    renderer = RemotionRenderer(settings.render)

    available, reason = renderer.is_available()
    assert available, reason

    output = store.path("entrega", "video.pt-br.mp4")
    result = await renderer.render(
        props,
        store.path("montagem", "props.pt-br.json"),
        output,
        public_dir=store.root,
    )

    assert output.exists()
    assert output.stat().st_size > 10_000, "MP4 pequeno demais para ter conteudo"
    #  Caixa ftyp no inicio: e um MP4 de verdade, nao um arquivo vazio.
    assert b"ftyp" in output.read_bytes()[:32]
    assert result.duration_s > 0


async def test_subtitles_can_be_burned_in(settings, cena_pronta) -> None:
    store, props = cena_pronta
    #  `model_copy` nao valida: os cues precisam ser objetos, senao a
    #  serializacao das props sai com dicionarios crus e o Remotion recebe
    #  algo que o contrato nao previu.
    burned = props.model_copy(
        update={
            "burnSubtitles": True,
            "subtitles": [
                SubtitleCue(start=0.0, end=2.0, text="Primeira"),
                SubtitleCue(start=2.0, end=4.0, text="legenda."),
            ],
        }
    )
    output = store.path("entrega", "video.legendado.mp4")
    await RemotionRenderer(settings.render).render(
        burned, store.path("montagem", "props.legendado.json"), output, public_dir=store.root
    )
    assert output.exists() and output.stat().st_size > 10_000
