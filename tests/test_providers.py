"""Adaptadores de provedores.

Dois contratos importam: todo provedor registra custo, e trocar de provedor e
trocar configuracao (CLAUDE.md).
"""

from __future__ import annotations

import pytest

from mundoantigo.errors import ConfigError, ProviderError, ProviderMisconfigured
from mundoantigo.providers import ProviderRegistry
from mundoantigo.providers.align import FakeAlign, WordTiming
from mundoantigo.providers.align.base import AlignmentResult
from mundoantigo.providers.image import FakeImage, ImageRequest
from mundoantigo.providers.llm import FakeLLM, parse_json_loose
from mundoantigo.providers.llm.base import strip_trailing_commas
from mundoantigo.providers.search import FakeSearch, SearchHit
from mundoantigo.providers.tts import ElevenLabsTTS, FakeTTS, SpeechRequest


class TestRegistry:
    def test_default_providers_come_from_yaml(self, settings, recorder) -> None:
        registry = ProviderRegistry(settings=settings, costs=recorder)
        assert registry.llm().name == "openrouter"
        assert registry.tts().is_local  # kokoro e o padrao enquanto o teste cego nao decide

    def test_fast_model_differs_from_main(self, settings, recorder) -> None:
        registry = ProviderRegistry(settings=settings, costs=recorder)
        assert registry.llm(fast=True).model != registry.llm().model

    def test_swapping_provider_is_a_config_change(self, settings, recorder) -> None:
        """A promessa do CLAUDE.md, verificada."""
        registry = ProviderRegistry(settings=settings, costs=recorder)
        assert registry.tts(name="elevenlabs").name == "elevenlabs"
        assert registry.image(name="openrouter").name == "openrouter"

    def test_unknown_provider_fails_clearly(self, settings, recorder) -> None:
        registry = ProviderRegistry(settings=settings, costs=recorder)
        with pytest.raises(ConfigError, match="sem bloco de configuracao"):
            registry.llm(name="inventado")

    def test_describe_lists_everything(self, settings, recorder) -> None:
        described = ProviderRegistry(settings=settings, costs=recorder).describe()
        assert set(described) == {"llm", "imagem", "tts", "alinhamento", "busca", "referencias"}


class TestCostIntegration:
    """Todo provedor passa pelo registrador. Nenhuma excecao."""

    async def test_llm_records_tokens(self, recorder, make_video) -> None:
        make_video("v1")
        llm = FakeLLM(costs=recorder, responses=['{"ok": true}'])
        await llm.complete("um prompt qualquer", step="roteiro", video_id="v1")
        steps = {s: n for s, _, n in recorder.breakdown_by_step()}
        assert steps["roteiro"] == 1

    async def test_image_records_one_per_image(self, recorder, tmp_path, make_video) -> None:
        make_video("v1")
        image = FakeImage(costs=recorder)
        for i in range(3):
            await image.generate(
                ImageRequest(prompt="cena"), tmp_path / f"c{i}.png", step="assets", video_id="v1"
            )
        steps = {s: n for s, _, n in recorder.breakdown_by_step()}
        assert steps["assets"] == 3

    async def test_tts_records_characters(self, recorder, tmp_path, make_video) -> None:
        make_video("v1")
        tts = FakeTTS(costs=recorder)
        result = await tts.synthesize(
            SpeechRequest(text="a" * 1500, voice_id="v", language="pt-BR"),
            tmp_path / "n.wav",
            step="narracao",
            video_id="v1",
        )
        assert result.characters == 1500

    async def test_search_records_one_per_query(self, recorder, make_video) -> None:
        make_video("v1")
        search = FakeSearch(costs=recorder)
        await search.search("aquedutos", step="pesquisa", video_id="v1")
        assert len(search.queries) == 1


class TestFakes:
    async def test_fake_image_writes_valid_png(self, recorder, tmp_path) -> None:
        image = FakeImage(costs=recorder)
        target = tmp_path / "cena.png"
        await image.generate(ImageRequest(prompt="x", seed=7), target, step="assets")
        assert target.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    async def test_fake_image_seed_is_deterministic(self, recorder, tmp_path) -> None:
        image = FakeImage(costs=recorder)
        a, b = tmp_path / "a.png", tmp_path / "b.png"
        await image.generate(ImageRequest(prompt="x", seed=42), a, step="assets")
        await image.generate(ImageRequest(prompt="x", seed=42), b, step="assets")
        assert a.read_bytes() == b.read_bytes()

    async def test_fake_tts_writes_valid_wav(self, recorder, tmp_path) -> None:
        import wave

        tts = FakeTTS(costs=recorder)
        target = tmp_path / "n.wav"
        await tts.synthesize(
            SpeechRequest(text="palavra " * 100, voice_id="v", language="pt-BR"),
            target,
            step="narracao",
        )
        with wave.open(str(target), "rb") as fh:
            assert fh.getframerate() == 24_000
            assert fh.getnframes() > 0

    async def test_fake_align_covers_full_duration(self, recorder, tmp_path) -> None:
        tts = FakeTTS(costs=recorder)
        audio = tmp_path / "n.wav"
        text = "uma frase de teste com varias palavras"
        await tts.synthesize(
            SpeechRequest(text=text, voice_id="v", language="pt-BR"), audio, step="narracao"
        )
        result = await FakeAlign(costs=recorder).align(
            audio, text, language="pt-BR", step="narracao"
        )
        assert len(result.words) == len(text.split())
        assert result.words[-1].end == pytest.approx(result.duration_s, rel=0.01)


class TestJSONParsing:
    """Todo prompt pede JSON sem cercas, e todo modelo devolve cercas as vezes."""

    def test_plain_json(self) -> None:
        assert parse_json_loose('{"a": 1}') == {"a": 1}

    def test_fenced_json(self) -> None:
        assert parse_json_loose('```json\n{"a": 1}\n```') == {"a": 1}

    def test_fence_without_language(self) -> None:
        assert parse_json_loose('```\n{"a": 1}\n```') == {"a": 1}

    def test_json_with_prose_around_it(self) -> None:
        assert parse_json_loose('Claro! Aqui vai:\n{"a": 1}\nEspero que ajude.') == {"a": 1}

    def test_array_response(self) -> None:
        assert parse_json_loose("[1, 2, 3]") == [1, 2, 3]

    def test_garbage_raises_with_context(self) -> None:
        with pytest.raises(ProviderError, match="nao e JSON valido"):
            parse_json_loose("desculpe, nao consigo fazer isso")

    def test_trailing_commas_are_tolerated(self) -> None:
        #  Amostra de 29/09: o modelo rapido deixou uma virgula antes do ].
        text = '{"paragrafos": ["um, dois", "tres",\n  ],\n "tags": ["a",],}'
        assert parse_json_loose(text) == {"paragrafos": ["um, dois", "tres"], "tags": ["a"]}

    def test_commas_inside_strings_are_kept(self) -> None:
        assert strip_trailing_commas('{"a": "x, ]", "b": [1,]}') == '{"a": "x, ]", "b": [1]}'
        escaped = r'{"a": "diz \"oi\", ]", "b": [2 ,  ]}'
        assert parse_json_loose(escaped) == {"a": 'diz "oi", ]', "b": [2]}


class TestSubtitles:
    def test_srt_breaks_on_sentences(self) -> None:
        words = [
            WordTiming("Primeira", 0.0, 0.5),
            WordTiming("frase.", 0.5, 1.0),
            WordTiming("Segunda", 1.0, 1.5),
            WordTiming("frase.", 1.5, 2.0),
        ]
        srt = AlignmentResult(tuple(words), 2.0, "fake", "m").to_srt()
        assert srt.count("-->") == 2
        assert "00:00:00,000 --> 00:00:01,000" in srt

    def test_srt_respects_char_limit(self) -> None:
        words = [WordTiming(f"palavra{i}", i * 0.4, (i + 1) * 0.4) for i in range(30)]
        srt = AlignmentResult(tuple(words), 12.0, "fake", "m").to_srt(max_chars=40)
        blocks = [b for b in srt.split("\n\n") if b.strip()]
        assert len(blocks) > 1
        for block in blocks:
            for line in block.splitlines()[2:]:
                assert len(line) <= 40

    def test_srt_timestamps_are_monotonic(self) -> None:
        words = [WordTiming(f"p{i}", i * 0.5, (i + 1) * 0.5) for i in range(20)]
        srt = AlignmentResult(tuple(words), 10.0, "fake", "m").to_srt()
        times = [line for line in srt.splitlines() if "-->" in line]
        starts = [t.split(" --> ")[0] for t in times]
        assert starts == sorted(starts)


class TestMissingCredentials:
    async def test_paid_provider_without_key_fails_permanently(
        self, recorder, tmp_path, monkeypatch
    ) -> None:
        """Chave ausente e erro permanente: retentar nao ajuda."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        tts = ElevenLabsTTS(costs=recorder, model="eleven_multilingual_v2")
        with pytest.raises(ProviderMisconfigured, match="ELEVENLABS_API_KEY"):
            await tts.synthesize(
                SpeechRequest(text="oi", voice_id="v", language="pt-BR"),
                tmp_path / "n.wav",
                step="narracao",
            )

    async def test_no_cost_recorded_when_call_never_happened(
        self, recorder, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        tts = ElevenLabsTTS(costs=recorder, model="eleven_multilingual_v2")
        with pytest.raises(ProviderMisconfigured):
            await tts.synthesize(
                SpeechRequest(text="a" * 5000, voice_id="v", language="pt-BR"),
                tmp_path / "n.wav",
                step="narracao",
            )
        assert recorder.spent_this_month() == 0.0


class TestOpenRouterPayload:
    @staticmethod
    async def _payload(recorder, monkeypatch, config: dict) -> dict:
        from mundoantigo.providers.llm.openrouter import OpenRouterLLM

        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-teste")
        llm = OpenRouterLLM(costs=recorder, model="anthropic/claude-sonnet-5", config=config)
        sent: dict = {}

        async def fake_post(key: str, payload: dict) -> dict:
            sent.update(payload)
            return {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

        monkeypatch.setattr(llm, "_post", fake_post)
        response = await llm.complete("Responda em JSON.", step="teste")
        assert response.json() == {"ok": True}
        return sent

    async def test_asks_for_a_json_object_by_default(self, recorder, monkeypatch) -> None:
        sent = await self._payload(recorder, monkeypatch, {})
        assert sent["response_format"] == {"type": "json_object"}

    async def test_json_mode_can_be_turned_off(self, recorder, monkeypatch) -> None:
        sent = await self._payload(recorder, monkeypatch, {"modo_json": False})
        assert "response_format" not in sent


def test_trusted_domains_are_flagged() -> None:
    assert SearchHit("t", "https://cambridge.org/x", "s").is_trusted_domain
    assert SearchHit("t", "https://usp.edu.br/x", "s").is_trusted_domain
    assert not SearchHit("t", "https://blog-aleatorio.com/x", "s").is_trusted_domain
