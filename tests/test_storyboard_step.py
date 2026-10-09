"""Etapa de cenas no ritmo de ~3 s (ADR 0012): o prompt v7 recebe a faixa de
segundos e a marca de frase continuada, o storyboard sai marcado para o corte
seco e a camera de reserva passa pelos quatro movimentos."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.pipeline import Runner, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder

MARKER = "Quebre o roteiro"


def without_cameras(base: Callable[[str], str]) -> Callable[[str], str]:
    """O LLM esquece a camera de toda cena: a montagem escolhe a de reserva."""

    def answer(prompt: str) -> str:
        text = base(prompt)
        if MARKER not in prompt:
            return text
        data = json.loads(text)
        for scene in data["cenas"]:
            scene.pop("camera", None)
        return json.dumps(data, ensure_ascii=False)

    return answer


@pytest.fixture
def pipeline(settings, recorder, sessions, com_remotion) -> tuple[Runner, FakeLLM]:
    llm = FakeLLM(costs=recorder, responses=without_cameras(responder()))
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    return runner, llm


async def _storyboard(pipeline: tuple[Runner, FakeLLM]) -> tuple[dict, list[str]]:
    runner, llm = pipeline
    video_id = runner.queue.enqueue_video("Aquedutos romanos")
    await Worker(runner, poll_seconds=0).drain(limit=40)
    prompts = [c["prompt"] for c in llm.calls if MARKER in c["prompt"]]
    return ArtifactStore(video_id).read_json("cenas", "storyboard.json"), prompts


async def test_the_prompt_gets_the_pace_and_the_continued_sentences(pipeline) -> None:
    storyboard, prompts = await _storyboard(pipeline)
    assert prompts
    assert all("{ritmo}" not in p for p in prompts)
    assert "de 2 a 4,5 segundos" in prompts[0]
    assert "no primeiro minuto" in prompts[0]
    assert all('"continua_frase"' in p for p in prompts)
    assert storyboard["transicoes"] == "capitulos"
    assert storyboard["ritmo"]["alvo"] == 3.0
    assert storyboard["ritmo"]["abertura"]["segundos"] == 60


async def test_the_fallback_camera_goes_through_the_four_moves(pipeline) -> None:
    """Antes, a posicao contava a cena duas vezes e so dois movimentos saiam."""
    storyboard, _ = await _storyboard(pipeline)
    cameras = [s["camera"] for s in storyboard["cenas"]]
    assert len(cameras) >= 4
    assert set(cameras[:4]) == {"zoom_in", "zoom_out", "pan_left", "pan_right"}
