"""Cortes verticais do TikTok (ADR 0010): o codigo mede, o LLM escolhe.

Os candidatos cabem na duracao nos idiomas das contas que postam, a escolha
do LLM e conferida antes de qualquer render, as props do corte comecam do
zero com o gancho e o cartao do fim, e a etapa nao paga a escolha duas vezes.
"""

from __future__ import annotations

import dataclasses
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
#  O desenho de 06/10, com as duas contas postando, e o de 08/10, com a EN parada.
TWO_ACCOUNTS = {"pt-br": 3, "en": 3}
EN_PAUSED = {"pt-br": 6, "en": 0}


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

    def test_a_paused_language_does_not_limit_the_duration(self, production) -> None:
        """Com a conta EN parada, o trecho EN longo demais nao derruba o PT."""
        storyboard, timings = production
        tight = ClipsConfig(en_range=(65.0, 70.0))
        both = candidates(storyboard, timings, tight)
        pt_only = candidates(storyboard, timings, tight, ("pt-br",))
        assert len(pt_only) > len(both)
        assert any(c.span("en").duration > 70.0 for c in pt_only)
        assert len(pt_only) == len(candidates(storyboard, timings, CONFIG, ("pt-br",)))

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


def _by_account(picks: list[tuple[str, str]]) -> dict[str, Any]:
    """Escolha no formato v2: cada corte numa conta, com os textos dela."""
    texts = {"pt": ("Gancho", "Legenda\nO que você acha?"), "en": ("Hook", "Caption")}
    return {
        "cortes": [
            {
                "candidato": cid,
                "conta": account,
                "gancho": f"{texts[account][0]} {cid}",
                "legenda": f"{texts[account][1]} {cid}",
                "hashtags": ["#historia", "#egito"] if account == "pt" else ["#history"],
            }
            for cid, account in picks
        ],
        "video_inteiro": {
            "legenda": {"pt": "Documentário completo"},
            "hashtags": {"pt": ["#historia", "#egito"]},
        },
    }


def _one_per_block(found: list[Any]) -> list[Any]:
    seen: dict[int, Any] = {}
    for candidate in found:
        seen.setdefault(candidate.block, candidate)
    return list(seen.values())


class TestSelectionByAccount:
    """Desde 06/10: cada conta com trechos proprios, para nao repetir imagens."""

    def test_each_account_gets_its_own_clips_in_its_language(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        a, b, c = _one_per_block(found)[:3]
        raw = _by_account([(a.id, "pt"), (b.id, "en"), (c.id, "pt")])
        selection = validate_selection(raw, found, CONFIG, FIXED, ("pt-br",))

        assert [clip.langs for clip in selection.clips] == [("pt-br",), ("en",), ("pt-br",)]
        assert [clip.number for clip in selection.for_lang("pt-br")] == [1, 3]
        en = selection.for_lang("en")[0]
        assert en.hook == {"en": f"Hook {b.id}"}
        assert en.hashtags["en"][0] == "#ancientworld"
        assert any("so 2 corte(s) em pt-br" in w for w in selection.warnings)
        assert any("so 1 corte(s) em en" in w for w in selection.warnings)
        #  So a conta PT posta o video inteiro: o EN nao precisa de legenda dele.
        assert set(selection.full_video) == {"pt-br"}
        assert not any("video inteiro" in w for w in selection.warnings)

    def test_the_same_stretch_cannot_go_to_both_accounts(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        first = found[0]
        twin = next(c for c in found[1:] if c.overlaps(first))
        with pytest.raises(SelectionError, match="sobrepoe"):
            validate_selection(
                _by_account([(first.id, "pt"), (twin.id, "en")]), found, CONFIG, FIXED
            )

    def test_extra_clips_for_a_full_account_are_ignored(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        a, b, c = _one_per_block(found)[:3]
        config = ClipsConfig(count=1)
        raw = _by_account([(a.id, "pt"), (b.id, "pt"), (c.id, "en")])
        selection = validate_selection(raw, found, config, FIXED, ("pt-br",))
        assert [(clip.candidate.id, clip.langs) for clip in selection.clips] == [
            (a.id, ("pt-br",)),
            (c.id, ("en",)),
        ]

    def test_unknown_account_is_refused(self, production) -> None:
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        raw = _by_account([(found[0].id, "pt")])
        raw["cortes"][0]["conta"] = "es"
        with pytest.raises(SelectionError, match="conta desconhecida"):
            validate_selection(raw, found, CONFIG, FIXED)

    def test_a_paused_account_gets_nothing(self, production) -> None:
        """Desde 08/10 a conta EN esta parada: o que vier para ela e ignorado."""
        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG, ("pt-br",))
        a, b, c = _one_per_block(found)[:3]
        raw = _by_account([(a.id, "pt"), (b.id, "en"), (c.id, "pt")])
        selection = validate_selection(raw, found, CONFIG, FIXED, ("pt-br",), counts=EN_PAUSED)
        assert [(clip.candidate.id, clip.langs) for clip in selection.clips] == [
            (a.id, ("pt-br",)),
            (c.id, ("pt-br",)),
        ]
        assert selection.warnings == ["so 2 corte(s) em pt-br, o pedido era 6"]
        #  Uma escolha sem `conta` vai so para a conta que posta.
        old = validate_selection(_choice(found, [a.id]), found, CONFIG, FIXED, counts=EN_PAUSED)
        assert old.clips[0].langs == ("pt-br",)

    def test_a_choice_in_the_old_format_still_posts_in_both(self, production) -> None:
        """As Piramides foram escolhidas antes da mudanca e seguem validas."""
        from mundoantigo.clips import Selection

        storyboard, timings = production
        found = candidates(storyboard, timings, CONFIG)
        selection = validate_selection(_choice(found, [found[0].id]), found, CONFIG, FIXED)
        assert selection.clips[0].langs == ("pt-br", "en")
        saved = selection.to_dict()
        for clip in saved["cortes"]:
            del clip["idiomas"]
        assert Selection.from_dict(saved).clips[0].langs == ("pt-br", "en")


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


def _with_accounts(settings, counts: dict[str, int]):
    """As configuracoes com a quantidade de cortes de cada conta (`tiktok.cortes`)."""
    channels = {
        lang: dataclasses.replace(channel, tiktok={**channel.tiktok, "cortes": counts[lang]})
        for lang, channel in settings.channels.items()
    }
    return dataclasses.replace(settings, channels=channels)


@pytest.fixture
def make_setup(settings, recorder, sessions, com_remotion, production):
    def build(counts: dict[str, int]):
        return _step_setup(_with_accounts(settings, counts), recorder, sessions, production)

    return build


@pytest.fixture
def step_setup(make_setup):
    """As duas contas postando, 3 cortes cada: o desenho de 06/10."""
    return make_setup(TWO_ACCOUNTS)


def _step_setup(settings, recorder, sessions, production):
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
    async def test_each_account_renders_only_its_own_clips(self, step_setup) -> None:
        runner, llm, store = step_setup
        ctx = runner.context_for_video(store.video_id)
        result = await CortesStep().run(ctx)

        assert result.ok, result.summary
        selection = store.read_json("cortes", "selecao.json")
        #  Tres blocos com trecho que cabe: o ensaio alterna as contas.
        accounts = {c["numero"]: c["idiomas"] for c in selection["cortes"]}
        assert accounts == {1: ["pt-br"], 2: ["en"], 3: ["pt-br"]}
        for n, langs in accounts.items():
            for lang in ("pt-br", "en"):
                rendered = store.is_complete(clip_video(ctx, n, lang))
                assert rendered is (lang in langs), (n, lang)
                if not rendered:
                    continue
                props = json.loads(store.path("cortes", f"props.{lang}.{n}.json").read_text())
                assert props["width"] == 1080 and props["height"] == 1920
                assert props["narration"] == f"cortes/narracao.{lang}.{n}.wav"
                assert store.path("cortes", f"narracao.{lang}.{n}.wav").exists()
        #  O prompt leva os candidatos com texto nos dois idiomas e a regra das contas.
        prompt = _clip_prompts(llm)[0]
        assert "### c01" in prompt and "PT: Frase" in prompt and "EN: Frase" in prompt
        assert "nunca postam o mesmo trecho" in prompt
        assert "fixado no perfil da conta PT" in prompt
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
        assert store.is_complete(clip_video(ctx, 2, "en"))

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


class TestReview:
    """Os cortes no corte final: comentario por corte e a troca pela sessao."""

    async def test_comment_on_a_clip_finds_the_scene_of_that_moment(self, step_setup) -> None:
        from mundoantigo.review import final_cut

        runner, _, store = step_setup
        await CortesStep().run(runner.context_for_video(store.video_id))
        entry = final_cut.add(store, "pt-br", 12.0, clip=3)
        assert entry["corte"] == 3 and entry["cena"] is not None
        props = json.loads(store.path("cortes", "props.pt-br.3.json").read_text())
        expected = max(s["index"] for s in props["scenes"] if s["start"] <= 12.0)
        assert entry["cena"] == expected
        assert final_cut.add(store, "en", 3.0)["corte"] is None
        with pytest.raises(final_cut.CommentError, match="nao existe"):
            final_cut.add(store, "pt-br", 1.0, clip=9)

    async def test_page_lists_the_clips_with_hook_and_caption(self, step_setup) -> None:
        from mundoantigo.web.views import clips_view

        runner, _, store = step_setup
        await CortesStep().run(runner.context_for_video(store.video_id))
        view = clips_view(store)
        assert [c["numero"] for c in view["idiomas"]["pt-br"]] == [1, 3]
        assert [c["numero"] for c in view["idiomas"]["en"]] == [2]
        first = view["idiomas"]["pt-br"][0]
        assert first["url"].endswith("/cortes/corte-1.pt-br.mp4")
        assert first["gancho"] and first["legenda"] and first["hashtags"][0] == "#mundoantigo"
        assert view["idiomas"]["en"][0]["hashtags"][0] == "#ancientworld"
        #  O video inteiro fica so na conta PT.
        assert view["video_inteiro"]["pt-br"]["legenda"]
        assert "en" not in view["video_inteiro"]

    async def test_session_edits_a_hook_and_only_that_clip_renders_again(
        self, step_setup, monkeypatch
    ) -> None:
        import argparse

        from mundoantigo import cli
        from mundoantigo.cli_review import cmd_cortes_editar

        runner, llm, store = step_setup
        ctx = runner.context_for_video(store.video_id)
        await CortesStep().run(ctx)
        monkeypatch.setattr(cli, "_runner", lambda **_: runner)
        args = argparse.Namespace(
            video_id=store.video_id,
            corte=3,
            candidato=None,
            gancho_pt="Gancho novo",
            gancho_en=None,
            legenda_pt=None,
            legenda_en=None,
        )
        assert cmd_cortes_editar(args) == 0

        assert not clip_video(ctx, 3, "pt-br").exists()
        assert clip_video(ctx, 1, "pt-br").exists(), "os outros cortes ficam"
        selection = store.read_json("cortes", "selecao.json")
        assert selection["cortes"][2]["gancho"]["pt-br"] == "Gancho novo"
        await CortesStep().run(ctx)
        assert len(_clip_prompts(llm)) == 1, "editar nao chama o LLM"
        props = json.loads(store.path("cortes", "props.pt-br.3.json").read_text())
        hook = props["overlays"][0]
        assert (hook["kind"], hook["text"]) == ("gancho", "Gancho novo")

        #  O corte 2 e so da conta EN: nao ha gancho PT para mudar.
        with pytest.raises(ValueError, match="so e postado em en"):
            cmd_cortes_editar(argparse.Namespace(**{**vars(args), "corte": 2}))


class TestPausedAccount:
    """Desde 08/10: a conta EN parada, e a PT com os trechos que eram dela."""

    async def test_only_the_pt_account_gets_clips_and_renders(self, make_setup) -> None:
        runner, llm, store = make_setup(EN_PAUSED)
        ctx = runner.context_for_video(store.video_id)
        result = await CortesStep().run(ctx)

        assert result.ok, result.summary
        selection = store.read_json("cortes", "selecao.json")
        #  Tres blocos com trecho que cabe: os tres vao para a conta PT.
        assert [c["idiomas"] for c in selection["cortes"]] == [["pt-br"]] * 3
        assert selection["avisos"] == ["so 3 corte(s) em pt-br, o pedido era 6"]
        for n in (1, 2, 3):
            assert store.is_complete(clip_video(ctx, n, "pt-br"))
        assert not list((store.root / "cortes").glob("*.en.*")), "nada do EN no disco"

        #  O prompt pede so a conta PT, sem o texto EN dos candidatos.
        prompt = _clip_prompts(llm)[0]
        assert "- PT: 6 cortes." in prompt and "- EN: parada." in prompt
        assert "PT: Frase" in prompt and "EN: Frase" not in prompt
        assert "nunca postam o mesmo trecho" not in prompt
        assert "posta só os cortes" not in prompt, "a conta EN parada nao posta corte nenhum"
        assert CortesStep().is_satisfied(ctx)

    async def test_no_account_posting_skips_the_llm(self, make_setup) -> None:
        runner, llm, store = make_setup({"pt-br": 0, "en": 0})
        ctx = runner.context_for_video(store.video_id)
        result = await CortesStep().run(ctx)
        assert result.ok and "nenhuma conta" in result.summary
        assert not _clip_prompts(llm)
        assert CortesStep().is_satisfied(ctx)


def test_step_order_is_seventeen() -> None:
    from mundoantigo.pipeline.state import spec

    assert spec(StepName.CORTES).ordinal == 15
    assert spec(StepName.ENTREGA).ordinal == 17
