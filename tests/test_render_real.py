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
from mundoantigo.render import (
    CardPiece,
    CardProps,
    HostProps,
    OverlayCue,
    RemotionRenderer,
    SceneProps,
    SubtitleCue,
    VideoProps,
)

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
    #  Peca de cartao e MC recortado: PNGs simples bastam para exercitar o layout.
    store.path("assets", "cena-003-peca-1.png").write_bytes(_solid_png(200, 200, (200, 160, 90)))
    (store.stage("assets") / "mc").mkdir(exist_ok=True)
    store.path("assets", "mc/joinha.png").write_bytes(_solid_png(100, 200, (240, 230, 210)))

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
                kind="cartao" if index == 3 else "lugar",
                card=(
                    CardProps(
                        pieces=[CardPiece(image="assets/cena-003-peca-1.png", label="DOLABRA")]
                    )
                    if index == 3
                    else None
                ),
                host=(
                    HostProps(image="assets/mc/joinha.png", side="direita", aspect=0.5)
                    if index == 3
                    else None
                ),
            )
            for index in range(1, 4)
        ],
        overlays=[
            OverlayCue(kind="titulo", start=0.0, duration=3.0, text="Antes do sol"),
            OverlayCue(kind="tarja", start=0.3, duration=2.5, text="Acampamento romano, século I"),
            OverlayCue(kind="texto", start=2.2, duration=1.5, text="16.800 homens"),
            OverlayCue(kind="balao", start=4.2, duration=1.5, text="Serviu ontem.", scene=3),
        ],
        palette=settings.style.palette,
    )
    return store, props


async def test_renders_a_playable_mp4(settings, cena_pronta) -> None:
    store, props = cena_pronta
    renderer = RemotionRenderer(settings.render)

    available, reason = renderer.is_available()
    assert available, reason

    output = store.path("montagem", "video.pt-br.mp4")
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
    output = store.path("montagem", "video.legendado.mp4")
    await RemotionRenderer(settings.render).render(
        burned, store.path("montagem", "props.legendado.json"), output, public_dir=store.root
    )
    assert output.exists() and output.stat().st_size > 10_000
