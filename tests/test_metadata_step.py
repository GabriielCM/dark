"""Etapas de cenas (conceito da thumb), metadados e entrega na fase B8: o
texto pago nao e pedido duas vezes, o motivo da refacao chega ao prompt e o
pacote tem uma pasta por idioma."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.errors import TransientError
from mundoantigo.pipeline import Runner, StepName, Worker
from mundoantigo.pipeline.steps.s07_cenas import CenasStep
from mundoantigo.pipeline.steps.s13_metadados import MetadadosStep
from mundoantigo.pipeline.steps.s17_entrega import link_or_copy
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from tests.fakes import responder

MARKER = "metadados de publicação"


def metadata_prompts(llm: FakeLLM) -> list[str]:
    return [c["prompt"] for c in llm.calls if MARKER in c["prompt"]]


@pytest.fixture
def pipeline(settings, recorder, sessions, com_remotion) -> tuple[Runner, FakeLLM]:
    llm = FakeLLM(costs=recorder, responses=responder())
    runner = Runner.build(
        settings=settings,
        providers=fake_registry(settings, recorder, llm=llm),
        session_factory=sessions,
    )
    return runner, llm


async def drain(runner: Runner) -> None:
    await Worker(runner, poll_seconds=0).drain(limit=80)


class TestMetadataStep:
    async def test_resume_does_not_pay_for_the_text_again(self, pipeline) -> None:
        runner, llm = pipeline
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        assert len(metadata_prompts(llm)) == 2

        #  Uma falha depois da chamada: a thumb EN nao chegou a ser gravada.
        store = ArtifactStore(video_id)
        store.delete(store.path("metadados", "thumb-com-texto.en.jpg"))
        runner.queue.reset_step(video_id, StepName.METADADOS)
        await drain(runner)

        assert len(metadata_prompts(llm)) == 2
        assert store.is_complete(store.path("metadados", "thumb-com-texto.en.jpg"))

    async def test_redo_sends_the_reviewer_reason_to_the_prompt(self, pipeline) -> None:
        runner, llm = pipeline
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)
        video = store.path("montagem", "video.pt-br.mp4")
        rendered_at = video.stat().st_mtime_ns

        affected = runner.redo(
            video_id, [StepName.METADADOS], reason="titulo generico demais, cite o Pont du Gard"
        )
        await drain(runner)

        assert StepName.MONTAGEM not in affected
        prompts = metadata_prompts(llm)
        assert len(prompts) == 4
        assert "cite o Pont du Gard" in prompts[-1]
        assert "cite o Pont du Gard" not in prompts[0]
        #  Metadados novos nao renderizam o video de novo.
        assert video.stat().st_mtime_ns == rendered_at

    async def test_description_and_warnings(self, pipeline) -> None:
        runner, _ = pipeline
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        pt = ArtifactStore(video_id).read_json("metadados", "metadados.pt-br.json")

        assert pt["titulo"] == "A água que subia sozinha"
        assert len(pt["titulos_alternativos"]) == 2
        assert pt["descricao"].startswith("Como os aquedutos romanos moviam")
        assert pt["capitulos"][0] == {"tempo": "00:00", "titulo": "A agua sem bomba"}
        assert pt["thumbnail"]["texto"] == "SEM BOMBAS"
        assert pt["thumbnail"]["lado"] == "direita"
        assert pt["descricao_bytes"] <= 5000
        #  O roteiro de teste tem 2 blocos: o YouTube so mostra capitulos com 3.
        assert any("capítulo" in w for w in pt["avisos"])

    def test_v1_answer_still_gives_the_paragraphs(self) -> None:
        written = MetadadosStep._validated(
            {
                "titulo": "Titulo",
                "descricao": "Paragrafo um.\n\nParagrafo dois.\n\n00:00 Abertura\n\nFontes: x",
                "tags": ["a"],
                "thumbnail": {"texto": "TEXTO"},
            }
        )
        assert written["paragrafos"] == ["Paragrafo um.", "Paragrafo dois."]
        assert written["thumbnail_texto"] == "TEXTO"

    def test_answer_without_title_is_retried(self) -> None:
        with pytest.raises(TransientError):
            MetadadosStep._validated({"paragrafos": ["x"]})


SCENES = [
    {"indice": 1, "tipo": "atuada", "descricao_visual": "the host pointing"},
    {"indice": 2, "tipo": "lugar", "descricao_visual": "Pont du Gard at dawn"},
]


class TestThumbnailConcept:
    def test_concept_from_the_llm(self, settings) -> None:
        concept = CenasStep._thumbnail_concept(
            {
                "conceito": "arco contra o céu",
                "descricao_visual": "one arch, low angle",
                "mc": {"acao": "looking up", "expressao": "amazed"},
                "lado_texto": "direita",
            },
            SCENES,
            settings.style,
            [],
            "cenas/thumbnail@v1",
        )
        assert concept["lado_texto"] == "direita"
        assert concept["mc"] == {"acao": "looking up", "expressao": "amazed"}
        assert concept["origem"] == "cenas/thumbnail@v1"

    def test_bad_answer_falls_back_to_the_first_place(self, settings) -> None:
        concept = CenasStep._thumbnail_concept(
            None, SCENES, settings.style, [], "cenas/thumbnail@v1"
        )
        assert concept["descricao_visual"] == "Pont du Gard at dawn"
        assert concept["mc"] is None
        assert concept["lado_texto"] == "esquerda"
        assert concept["origem"] == "fallback"


class TestDeliveryFiles:
    def test_hard_link_when_possible(self, tmp_path: Path) -> None:
        source = tmp_path / "video.pt-br.mp4"
        source.write_bytes(b"mp4")
        target = tmp_path / "entrega" / "video.mp4"
        target.parent.mkdir()
        link_or_copy(source, target)
        assert target.stat().st_ino == source.stat().st_ino

    def test_copy_when_the_link_fails(self, tmp_path: Path, monkeypatch) -> None:
        def no_link(*_args: object) -> None:
            raise OSError("outro volume")

        monkeypatch.setattr(os, "link", no_link)
        source = tmp_path / "video.pt-br.mp4"
        source.write_bytes(b"mp4")
        target = tmp_path / "video.mp4"
        target.write_bytes(b"antigo")
        link_or_copy(source, target)
        assert target.read_bytes() == b"mp4"
        assert target.stat().st_ino != source.stat().st_ino
