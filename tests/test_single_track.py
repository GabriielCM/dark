"""Faixa unica de audio (ADR 0011): a adaptacao cabe no tempo do PT, as duas
narracoes saem na mesma linha do tempo e o pacote leva a faixa EN."""

from __future__ import annotations

import dataclasses
import json
import shutil
import wave
from collections.abc import Callable

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.config import NarrationConfig
from mundoantigo.pipeline import Runner, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder

SHORTEN = "narration are too long"


def frames(path) -> int:
    with wave.open(str(path), "rb") as fh:
        return fh.getnframes()


def wordy_english() -> Callable[[str], str]:
    """A adaptacao EN do teste com cada bloco dobrado: passa do limite."""
    base = responder()

    def responde(prompt: str) -> str:
        out = base(prompt)
        if "Adapt this Brazilian" in prompt:
            data = json.loads(out)
            for block in data["blocos"]:
                block["narracao"] = f"{block['narracao']} {block['narracao']}"
            return json.dumps(data, ensure_ascii=False)
        return out

    return responde


def build(settings, recorder, sessions, *, single: bool, responses=None) -> tuple[Runner, FakeLLM]:
    settings = dataclasses.replace(settings, narration=NarrationConfig(single_track=single))
    llm = FakeLLM(costs=recorder, responses=responses or responder())
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    return runner, llm


async def drain(runner: Runner) -> None:
    await Worker(runner, poll_seconds=0).drain(limit=80)


class TestSharedTimeline:
    async def test_both_narrations_end_up_with_the_same_blocks(
        self, settings, recorder, sessions, sem_remotion
    ) -> None:
        runner, _ = build(settings, recorder, sessions, single=True)
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        pt = store.path("narracao", "narracao.pt-br.wav")
        en = store.path("narracao", "narracao.en.wav")
        assert frames(pt) == frames(en)
        for lang in ("pt-br", "en"):
            assert store.path("narracao", f"natural.{lang}.wav").exists()
        tempos = {
            lang: store.read_json("narracao", f"tempos.{lang}.json") for lang in ("pt-br", "en")
        }
        assert tempos["pt-br"]["duracao_s"] == tempos["en"]["duracao_s"]
        starts = {lang: [b["inicio_s"] for b in t["blocos"]] for lang, t in tempos.items()}
        assert starts["pt-br"] == pytest.approx(starts["en"], abs=1e-3)

        sidecar = store.read_sidecar(pt)
        assert sidecar is not None
        assert sidecar.model == "linha-unica"
        assert set(sidecar.extra["esticamento"]) == {
            str(b["indice"]) for b in tempos["pt-br"]["blocos"]
        }

    async def test_two_cut_mode_keeps_each_narration_natural(
        self, settings, recorder, sessions, sem_remotion
    ) -> None:
        runner, llm = build(settings, recorder, sessions, single=False, responses=wordy_english())
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        assert not store.path("narracao", "natural.pt-br.wav").exists()
        assert frames(store.path("narracao", "narracao.pt-br.wav")) != frames(
            store.path("narracao", "narracao.en.wav")
        )
        #  Sem a faixa unica, nao ha por que pagar o encurtamento.
        assert not [c for c in llm.calls if SHORTEN in c["prompt"]]


class TestWordLimits:
    async def test_long_english_blocks_are_shortened_once(
        self, settings, recorder, sessions, sem_remotion
    ) -> None:
        runner, llm = build(settings, recorder, sessions, single=True, responses=wordy_english())
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        adaptation = [c["prompt"] for c in llm.calls if "Adapt this Brazilian" in c["prompt"]]
        assert "at most" in adaptation[0]
        assert len([c for c in llm.calls if SHORTEN in c["prompt"]]) == 1

        sidecar = store.read_sidecar(store.path("adaptacao", "roteiro.en.json"))
        assert sidecar is not None
        extra = sidecar.extra
        assert extra["blocos_encurtados"]
        for words, limit in zip(
            extra["palavras_por_bloco"], extra["limites_palavras"], strict=True
        ):
            assert words <= limit
        #  A adaptacao e as frases EN que a narracao le saem do roteiro encurtado.
        roteiro = store.read_json("adaptacao", "roteiro.en.json")
        frases = store.read_json("adaptacao", "frases.en.json")
        assert sum(len(b["narracao"].split()) for b in roteiro["blocos"]) == sum(
            len(f["texto"].split()) for f in frases
        )

    def test_limit_follows_the_measured_pace_of_each_voice(self) -> None:
        from mundoantigo.pipeline.steps.s05_adaptacao_en import AdaptacaoEnStep

        roteiro = {"blocos": [{"narracao": " ".join(["palavra"] * 150)}, {"narracao": "uma"}]}
        assert AdaptacaoEnStep._word_limits(roteiro, 150, 137) == [137, 1]


class TestDelivery:
    @pytest.fixture
    def delivered(self, settings, recorder, sessions, com_remotion):
        async def run(single: bool) -> ArtifactStore:
            runner, _ = build(settings, recorder, sessions, single=single)
            video_id = runner.queue.enqueue_video("Aquedutos romanos")
            await drain(runner)
            runner.approve(video_id, reviewer="teste")
            await drain(runner)
            return ArtifactStore(video_id)

        return run

    async def test_package_carries_the_english_track(self, delivered) -> None:
        store = await delivered(True)
        pacote = store.read_json("entrega", "pacote.json")
        checklist = store.read_text("entrega", "CHECKLIST.md")

        assert pacote["faixa_unica"] is True
        assert "## Faixa em inglês no vídeo PT (ADR 0011)" in checklist
        assert "Dublagem e legenda em inglês" in checklist
        assert "(parado" not in checklist
        assert checklist.index("Faixa em inglês") < checklist.index("## Depois de publicar")
        #  O ingles vai no video PT: titulo, descricao e legenda EN, sem video EN.
        en = store.root / "entrega" / "en"
        assert (en / "legendas.srt").exists()
        assert (en / "publicacao.txt").exists()
        assert not (en / "video.mp4").exists()
        if shutil.which("ffmpeg"):
            track = store.root / "entrega" / "pt-br" / "faixa-en.m4a"
            assert track.stat().st_size > 0
            assert pacote["idiomas"]["pt-br"]["faixa_en"] == "entrega/pt-br/faixa-en.m4a"
        else:
            assert any("faixa EN" in a for a in pacote["idiomas"]["pt-br"]["avisos"])

    async def test_two_channel_package_is_unchanged(self, delivered) -> None:
        store = await delivered(False)
        checklist = store.read_text("entrega", "CHECKLIST.md")
        assert "Faixa em inglês" not in checklist
        assert "Dublagem e legenda em inglês" not in checklist
        assert not (store.root / "entrega" / "pt-br" / "faixa-en.m4a").exists()
        assert (store.root / "entrega" / "en" / "video.mp4").exists()


class TestMontage:
    """Com a faixa unica, o video EN nao e renderizado: o ingles e a dublagem do PT."""

    @pytest.fixture
    def reviewed(self, settings, recorder, sessions, com_remotion):
        async def run(single: bool) -> ArtifactStore:
            runner, _ = build(settings, recorder, sessions, single=single)
            video_id = runner.queue.enqueue_video("Aquedutos romanos")
            await drain(runner)
            return ArtifactStore(video_id)

        return run

    async def test_single_track_renders_only_the_portuguese_video(self, reviewed) -> None:
        store = await reviewed(True)
        assert store.path("montagem", "video.pt-br.mp4").exists()
        assert not store.path("montagem", "video.en.mp4").exists()
        #  As props EN ficam para um render manual, e situam os comentarios na dublagem.
        assert store.path("montagem", "props.en.json").exists()
        assert set(store.read_json("revisao", "revisao.json")["videos"]) == {"pt-br"}

    async def test_two_cut_mode_renders_both(self, reviewed) -> None:
        store = await reviewed(False)
        for lang in ("pt-br", "en"):
            assert store.path("montagem", f"video.{lang}.mp4").exists()

    async def test_final_cut_plays_the_english_dub(self, reviewed) -> None:
        from mundoantigo.review import final_cut as cut_comments
        from mundoantigo.web import views

        store = await reviewed(True)
        corte = views.final_cut(store)
        assert set(corte["videos"]) == {"pt-br"}
        assert corte["faixa_en"].endswith("/narracao/narracao.en.wav")
        #  O comentario no audio cai na cena daquele instante, como no video.
        comment = cut_comments.add(store, "en", 1.0)
        assert comment["chave"] is not None

    async def test_final_cut_without_single_track_has_no_dub_player(self, reviewed) -> None:
        from mundoantigo.web import views

        store = await reviewed(False)
        assert views.final_cut(store)["faixa_en"] is None
