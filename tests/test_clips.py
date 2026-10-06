"""Cortes verticais do TikTok (ADR 0010): o codigo mede, o LLM escolhe.

Os candidatos cabem na duracao nos dois idiomas, a escolha do LLM e
conferida antes de qualquer render, as props do corte comecam do zero com o
gancho e o cartao do fim, e a etapa nao paga a escolha duas vezes.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.clips import ClipsConfig, SelectionError, candidates, validate_selection
from mundoantigo.clips.candidates import TAIL_S, scene_openers
from mundoantigo.config import RenderConfig
from mundoantigo.errors import TransientError
from mundoantigo.pipeline import Runner, StepName
from mundoantigo.pipeline.steps.s15_cortes import CortesStep, clip_video
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.render.clips import clip_props, slice_wav
from mundoantigo.render.remotion import props_from_storyboard
from tests.fakes import responder

CONFIG = ClipsConfig()
#  Frases de 5 s (PT) com 0,5 s de pausa. O bloco 0 e curto demais para um
#  corte; o 1 e longo (varios inicios); o 2 e o 3 cabem inteiros.
BLOCKS = (6, 26, 15, 14)
EN_SCALE = 1.12
MARKER = "Escolha os cortes deste vídeo"


def _timings(prefix: str, scale: float) -> dict[str, Any]:
    frases: list[dict[str, Any]] = []
    palavras: list[dict[str, Any]] = []
    blocos: list[dict[str, Any]] = []
    t = 0.0
    n = 0
    for b, count in enumerate(BLOCKS):
        start = t
        for _ in range(count):
            n += 1
            length = 5.0 * scale
            first_word = len(palavras)
            for w in range(5):
                palavras.append(
                    {
                        "p": f"{prefix}{n}w{w}",
                        "i": round(t + w * length / 5, 3),
                        "f": round(t + (w + 1) * length / 5 - 0.05, 3),
                    }
                )
            frases.append(
                {
                    "id": f"{prefix}{n:04d}",
                    "bloco": b,
                    "inicio": round(t, 3),
                    "fim": round(t + length, 3),
                    "palavras": [first_word, first_word + 4],
                }
            )
            t += length + 0.5
        blocos.append(
            {
                "indice": b,
                "secao": "desenvolvimento",
                "titulo": f"Bloco {b}: teste",
                "inicio_s": round(start, 3),
                "fim_s": round(t - 0.5, 3),
            }
        )
    return {"duracao_s": round(t, 3), "palavras": palavras, "frases": frases, "blocos": blocos}


def _storyboard(pt: dict[str, Any]) -> dict[str, Any]:
    """Uma cena a cada duas frases, sempre comecando junto com a frase."""
    scenes: list[dict[str, Any]] = []
    by_block: dict[int, list[dict[str, Any]]] = {}
    for f in pt["frases"]:
        by_block.setdefault(int(f["bloco"]), []).append(f)
    for block, sentences in by_block.items():
        pairs = [sentences[i : i + 2] for i in range(0, len(sentences), 2)]
        for k, pair in enumerate(pairs):
            index = len(scenes) + 1
            scene: dict[str, Any] = {
                "indice": index,
                "bloco": block,
                "frases": [f["id"] for f in pair],
                "inicio_palavra": 0,
                "fracao_bloco": [k / len(pairs), (k + 1) / len(pairs)],
                "tipo": "lugar",
                "camera": "pan_left",
                "narracao": "texto",
            }
            if k == 0:
                scene["titulo_capitulo"] = {"pt": f"Bloco {block}: teste", "en": f"Block {block}"}
                scene["tarja"] = {"pt": "GIZÉ", "en": "GIZA"}
            if k == 1:
                scene["texto_chave"] = {"pt": "onze bois", "en": "eleven cattle"}
            scenes.append(scene)
    return {"versao": 2, "cenas": scenes}


@pytest.fixture
def production() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    pt = _timings("p", 1.0)
    en = _timings("e", EN_SCALE)
    return _storyboard(pt), {"pt-br": pt, "en": en}


def _choice(found: list[Any], ids: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "cortes": [
            {
                "candidato": cid,
                "gancho": {"pt": f"Gancho {cid}", "en": f"Hook {cid}"},
                "legenda": {"pt": f"Legenda {cid}\nO que você acha?", "en": f"Caption {cid}"},
                "hashtags": {"pt": ["#História", "#Egito Antigo"], "en": ["#history"]},
                **extra,
            }
            for cid in ids
        ],
        "video_inteiro": {
            "legenda": {"pt": "Documentário completo", "en": "Full documentary"},
            "hashtags": {"pt": ["#historia"], "en": ["#history"]},
        },
    }


FIXED = {"pt-br": "#mundoantigo", "en": "#ancientworld"}


class TestCandidates:
    def test_every_candidate_fits_in_both_languages(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        assert found
        for c in found:
            pt, en = c.span("pt-br"), c.span("en")
            assert CONFIG.pt_range[0] <= pt.duration <= CONFIG.pt_range[1], c
            assert CONFIG.en_range[0] <= en.duration <= CONFIG.en_range[1], c
        assert [c.id for c in found] == [f"c{n:02d}" for n in range(1, len(found) + 1)]

    def test_a_block_too_short_gives_no_candidate(self, production) -> None:
        storyboard, timings = production
        assert all(c.block != 0 for c in candidates(storyboard, timings, CONFIG))

    def test_a_block_that_fits_is_offered_whole(self, production) -> None:
        storyboard, timings = production
        whole = [c for c in candidates(storyboard, timings, CONFIG) if c.block == 2]
        pt = timings["pt-br"]
        block_sentences = [f["id"] for f in pt["frases"] if f["bloco"] == 2]
        assert any(
            c.span("pt-br").first == block_sentences[0]
            and c.span("pt-br").last == block_sentences[-1]
            for c in whole
        )
        #  No EN o mesmo bloco inteiro, de frase EN a frase EN.
        en_sentences = [f["id"] for f in timings["en"]["frases"] if f["bloco"] == 2]
        full = next(c for c in whole if c.span("pt-br").first == block_sentences[0])
        assert full.span("en").first == en_sentences[0]

    def test_cuts_start_where_a_scene_starts_and_end_after_the_last_word(self, production) -> None:
        storyboard, timings = production
        openers = scene_openers(storyboard)
        ends = {f["id"]: float(f["fim"]) for f in timings["pt-br"]["frases"]}
        for c in candidates(storyboard, timings, CONFIG):
            span = c.span("pt-br")
            assert span.first in openers
            #  Respiro depois da ultima palavra, ate o meio da pausa seguinte.
            assert ends[span.last] < span.end <= ends[span.last] + TAIL_S + 1e-6


class TestSelection:
    def test_choice_is_ordered_by_time_and_numbered(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        late, early = found[-1], found[0]
        selection = validate_selection(_choice(found, [late.id, early.id]), found, CONFIG, FIXED)
        assert [c.candidate.id for c in selection.clips] == [early.id, late.id]
        assert [c.number for c in selection.clips] == [1, 2]
        assert any("so 2 corte(s)" in w for w in selection.warnings)

    def test_hashtags_are_normalized_with_the_channel_tag_first(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        selection = validate_selection(_choice(found, [found[0].id]), found, CONFIG, FIXED)
        clip = selection.clips[0]
        assert clip.hashtags["pt-br"] == ["#mundoantigo", "#historia", "#egitoantigo"]
        assert clip.hashtags["en"][0] == "#ancientworld"
        #  So duas hashtags no EN: abaixo do minimo vira aviso, nao erro.
        assert any("(en)" in w and "hashtag" in w for w in selection.warnings)
        assert selection.full_video["pt-br"]["legenda"] == "Documentário completo"

    def test_unknown_candidate_is_refused(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        with pytest.raises(SelectionError, match="desconhecido"):
            validate_selection(_choice(found, ["c99"]), found, CONFIG, FIXED)

    def test_overlapping_choices_are_refused(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        first = found[0]
        twin = next(c for c in found[1:] if c.overlaps(first))
        with pytest.raises(SelectionError, match="sobrepoe"):
            validate_selection(_choice(found, [first.id, twin.id]), found, CONFIG, FIXED)

    def test_missing_hook_is_refused_and_long_hook_warned(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        empty = _choice(found, [found[0].id], gancho={"pt": "", "en": "Hook"})
        with pytest.raises(SelectionError, match="sem gancho"):
            validate_selection(empty, found, CONFIG, FIXED)
        long = _choice(
            found, [found[0].id], gancho={"pt": " ".join(["palavra"] * 12), "en": "Hook"}
        )
        selection = validate_selection(long, found, CONFIG, FIXED)
        assert any("gancho pt-br" in w for w in selection.warnings)


def _full_props(storyboard: dict[str, Any], timings: dict[str, Any]):
    return props_from_storyboard(
        video_id="v",
        language="pt-BR",
        title="t",
        storyboard=storyboard,
        timings=timings,
        narration_file="narracao/narracao.pt-br.wav",
        config=RenderConfig(
            fps=30, width=1920, height=1080, project="render", concurrency=1, crf=18
        ),
        palette={},
    )


class TestClipProps:
    def test_the_clip_starts_at_zero_with_hook_and_end_card(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        span = found[0].span("pt-br")
        props = clip_props(
            _full_props(storyboard, timings["pt-br"]),
            start=span.start,
            end=span.end,
            narration_file="cortes/narracao.pt-br.1.wav",
            hook="Onze bois por dia",
            end_text="Vídeo completo fixado no perfil",
            width=1080,
            height=1920,
            hook_s=3.0,
            end_s=2.5,
        )
        assert (props.width, props.height) == (1080, 1920)
        assert props.burnSubtitles is True
        assert props.durationInSeconds == pytest.approx(span.duration, abs=0.01)
        assert props.narration == "cortes/narracao.pt-br.1.wav"

        #  Cenas cobrem o corte inteiro, de zero ao fim, sem buraco.
        assert props.scenes[0].start == 0.0
        last = props.scenes[-1]
        assert last.start + last.duration == pytest.approx(props.durationInSeconds, abs=0.01)
        for before, after in zip(props.scenes, props.scenes[1:], strict=False):
            assert after.start == pytest.approx(before.start + before.duration, abs=0.01)

        kinds = [c.kind for c in props.overlays]
        assert kinds[0] == "gancho" and kinds[-1] == "fim"
        assert "titulo" not in kinds, "o gancho faz o papel do titulo de capitulo"
        for cue in props.overlays:
            assert cue.start >= 0 and cue.start + cue.duration <= props.durationInSeconds + 0.01
            if cue.kind in ("tarja", "texto"):
                #  O alto da tela e do gancho nos primeiros segundos e do cartao no fim.
                assert cue.start >= 3.0
                assert cue.start + cue.duration <= props.durationInSeconds - 2.5 + 0.01
        assert props.subtitles and props.subtitles[0].start >= 0
        assert all(s.end <= props.durationInSeconds + 0.01 for s in props.subtitles)

    def test_slice_wav_keeps_the_interval_with_a_short_fade(self, tmp_path: Path) -> None:
        source = tmp_path / "n.wav"
        rate = 8000
        with wave.open(str(source), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes((1000).to_bytes(2, "little", signed=True) * rate * 2)
        out = slice_wav(source, tmp_path / "c" / "corte.wav", 0.5, 1.25)
        with wave.open(str(out)) as w:
            assert w.getnframes() == int(0.75 * rate)
            frames = w.readframes(w.getnframes())
        first = int.from_bytes(frames[:2], "little", signed=True)
        middle = int.from_bytes(
            frames[len(frames) // 2 : len(frames) // 2 + 2], "little", signed=True
        )
        assert first == 0 and middle == 1000


# -- a etapa -------------------------------------------------------------------


def _write_wav(path: Path, seconds: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(seconds * 8000))


@pytest.fixture
def step_setup(settings, recorder, sessions, com_remotion, production):
    llm = FakeLLM(costs=recorder, responses=responder())
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    video_id = runner.queue.enqueue_video("Pirâmides", video_id="cortes")
    store = ArtifactStore(video_id)
    storyboard, timings = production
    store.write_json("cenas", "storyboard.json", storyboard, step="cenas")
    for lang in ("pt-br", "en"):
        store.write_json("narracao", f"tempos.{lang}.json", timings[lang], step="narracao")
        sentences = [
            {"id": f["id"], "bloco": f["bloco"], "texto": f"Frase {f['id']}."}
            for f in timings[lang]["frases"]
        ]
        store.write_json("narracao", f"frases.{lang}.json", sentences, step="narracao")
        _write_wav(store.path("narracao", f"narracao.{lang}.wav"), timings[lang]["duracao_s"])
    return runner, llm, store


def _clip_prompts(llm: FakeLLM) -> list[str]:
    return [c["prompt"] for c in llm.calls if MARKER in c["prompt"]]


class TestStep:
    async def test_renders_three_clips_in_both_languages(self, step_setup) -> None:
        runner, llm, store = step_setup
        ctx = runner.context_for_video(store.video_id)
        result = await CortesStep().run(ctx)

        assert result.ok, result.summary
        selection = store.read_json("cortes", "selecao.json")
        assert len(selection["cortes"]) == 3
        for n in (1, 2, 3):
            for lang in ("pt-br", "en"):
                assert store.is_complete(clip_video(ctx, n, lang))
                props = json.loads(store.path("cortes", f"props.{lang}.{n}.json").read_text())
                assert props["width"] == 1080 and props["height"] == 1920
                assert props["narration"] == f"cortes/narracao.{lang}.{n}.wav"
                assert store.path("cortes", f"narracao.{lang}.{n}.wav").exists()
        #  O prompt leva os candidatos com texto nos dois idiomas.
        prompt = _clip_prompts(llm)[0]
        assert "### c01" in prompt and "PT: Frase" in prompt and "EN: Frase" in prompt
        assert CortesStep().is_satisfied(ctx)

    async def test_resume_does_not_pay_for_the_choice_again(self, step_setup) -> None:
        runner, llm, store = step_setup
        ctx = runner.context_for_video(store.video_id)
        await CortesStep().run(ctx)
        #  Uma imagem refeita: os renders saem, a escolha paga fica.
        removed = CortesStep().invalidate(ctx, keep_paid=True)
        assert store.path("cortes", "selecao.json").exists()
        assert any(p.suffix == ".mp4" for p in removed)
        await CortesStep().run(ctx)
        assert len(_clip_prompts(llm)) == 1
        assert store.is_complete(clip_video(ctx, 1, "en"))

    async def test_redo_from_scratch_asks_again(self, step_setup) -> None:
        runner, llm, store = step_setup
        ctx = runner.context_for_video(store.video_id)
        await CortesStep().run(ctx)
        CortesStep().invalidate(ctx)
        assert not store.path("cortes", "selecao.json").exists()
        await CortesStep().run(ctx)
        assert len(_clip_prompts(llm)) == 2

    async def test_bad_choice_is_retried_without_caching(self, step_setup, recorder) -> None:
        runner, _, store = step_setup
        bad = FakeLLM(costs=recorder, responses=[json.dumps({"cortes": [{"candidato": "c99"}]})])
        runner.providers = fake_registry(runner.settings, recorder, llm=bad)
        ctx = runner.context_for_video(store.video_id)
        with pytest.raises(TransientError, match="desconhecido"):
            await CortesStep().run(ctx)
        assert not store.path("cortes", "llm.json").exists()

    async def test_short_video_ends_without_clips_or_llm(self, step_setup) -> None:
        runner, llm, store = step_setup
        timings = store.read_json("narracao", "tempos.pt-br.json")
        for f in timings["frases"]:
            f["bloco"] = 0
        timings["blocos"] = [{**timings["blocos"][0], "fim_s": 30.0}]
        store.write_json("narracao", "tempos.pt-br.json", timings, step="narracao")
        ctx = runner.context_for_video(store.video_id)
        result = await CortesStep().run(ctx)
        assert result.ok and "sem cortes" in result.summary
        assert not _clip_prompts(llm)
        assert CortesStep().is_satisfied(ctx)


def test_step_order_is_seventeen() -> None:
    from mundoantigo.pipeline.state import spec

    assert spec(StepName.CORTES).ordinal == 15
    assert spec(StepName.ENTREGA).ordinal == 17
