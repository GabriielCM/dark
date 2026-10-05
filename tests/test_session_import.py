"""Roteiro feito na sessao do Claude Code: validacao, importacao e fila.

O modo sessao troca as etapas pagas de pesquisa e roteiro por arquivos
importados; o gate de fatos continua valendo sobre eles.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import StepState, Video
from mundoantigo.pipeline import Runner, StepName, Worker
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM
from mundoantigo.session.importer import import_session
from tests.fakes import responder

FRASE = "Você acorda antes do sol, desmonta a tenda e segue a coluna pela estrada de pedra. "


def session_files(*, words: int = 2900, blocks: int = 5) -> dict[str, dict[str, Any]]:
    """Uma sessao valida: 5 blocos, ~2.900 palavras (meta de 18 a 22 min a 150 ppm)."""
    per_block = words // blocks
    base = FRASE.split()
    narration = " ".join((base * (per_block // len(base) + 1))[:per_block])
    return {
        "dossie.json": {
            "tema": "Um dia na vida de um legionário",
            "resumo": "A rotina de marcha.",
            "blocos": [
                {
                    "titulo": "Marcha",
                    "afirmacoes": [
                        {
                            "id": "d1",
                            "texto": "Marchavam cerca de 29 km por dia.",
                            "fontes": ["f1", "f2"],
                        },
                        {"id": "d2", "texto": "Montavam acampamento toda noite.", "fontes": ["f1"]},
                    ],
                }
            ],
            "fontes": [
                {"id": "f1", "titulo": "Vegécio", "url": "https://a.edu/vegecio", "tipo": "livro"},
                {
                    "id": "f2",
                    "titulo": "Marcha romana",
                    "url": "https://b.ac.uk/marcha",
                    "ano": 2019,
                },
            ],
        },
        "roteiro.pt-br.json": {
            "titulo_provisorio": "Um dia na vida de um legionário",
            "gancho": "Ainda é noite quando você acorda.",
            "figurino": "a cream tunic with leather straps and a black cloak",
            "blocos": [
                {
                    "secao": ["gancho", "contexto", "desenvolvimento", "revelacao", "fechamento"][
                        i % 5
                    ],
                    "titulo": f"Capítulo {i + 1}",
                    "narracao": narration,
                    "afirmacoes_usadas": ["d1"] if i == 0 else [],
                    "comentarios_mc": [
                        "Isso pesa mais do que parece.",
                        "Todo mundo sabe seu papel.",
                        "Passo, passo, passo. Sempre.",
                        "Nem a mula quer estar aqui.",
                    ],
                    "tarjas": ["ACAMPAMENTO ROMANO, SÉCULO I"] if i == 0 else [],
                }
                for i in range(blocks)
            ],
        },
        "relatorio_fatos.json": {
            "itens": [
                {
                    "id": "a1",
                    "afirmacao": "cerca de 29 km por dia",
                    "bloco": 0,
                    "fontes": ["f1", "f2"],
                    "confianca": "alta",
                    "justificativa": "duas fontes",
                },
                {
                    "id": "a2",
                    "afirmacao": "acampamento toda noite",
                    "bloco": 1,
                    "fontes": ["f1"],
                    "confianca": "media",
                    "justificativa": "uma fonte",
                },
            ]
        },
    }


def write_session(folder: Path, files: dict[str, dict[str, Any]]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, payload in files.items():
        (folder / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return folder


def _import(settings, folder: Path, store: ArtifactStore, **kw: Any):
    return import_session(
        folder, store, channel=settings.channel("pt-br"), facts=settings.facts, **kw
    )


class TestValidation:
    def test_a_valid_session_passes(self, settings, tmp_path) -> None:
        folder = write_session(tmp_path / "s", session_files())
        report = _import(settings, folder, ArtifactStore("v"), validate_only=True)
        assert report.ok, report.errors
        assert 2700 <= report.words <= 3100
        assert report.gate["aprovado"] is True

    @pytest.mark.parametrize(
        ("mutate", "expected"),
        [
            (
                lambda f: f["roteiro.pt-br.json"]["blocos"][0]["afirmacoes_usadas"].append("d9"),
                "fora do dossie",
            ),
            (
                lambda f: f["relatorio_fatos.json"]["itens"][0]["fontes"].append("f9"),
                "fontes fora do dossie",
            ),
            (lambda f: f["relatorio_fatos.json"]["itens"][0].update(bloco=9), "bloco 9"),
            (
                lambda f: f["roteiro.pt-br.json"].update(pedidos_de_pesquisa=["data da reforma"]),
                "ainda pede pesquisa",
            ),
            (lambda f: f["roteiro.pt-br.json"]["blocos"][0].update(campo_errado=1), "Extra inputs"),
        ],
    )
    def test_inconsistencies_are_errors(self, settings, tmp_path, mutate, expected) -> None:
        files = session_files()
        mutate(files)
        report = _import(settings, write_session(tmp_path / "s", files), ArtifactStore("v"))
        assert not report.ok
        assert any(expected in e for e in report.errors), report.errors

    def test_text_without_accents_is_refused(self, settings, tmp_path) -> None:
        files = session_files()
        for block in files["roteiro.pt-br.json"]["blocos"]:
            block["narracao"] = "voce acorda antes do sol " * 120
        report = _import(settings, write_session(tmp_path / "s", files), ArtifactStore("v"))
        assert any("acento" in e for e in report.errors)

    def test_length_outside_the_target_is_refused(self, settings, tmp_path) -> None:
        report = _import(
            settings, write_session(tmp_path / "s", session_files(words=1200)), ArtifactStore("v")
        )
        assert any("fora da meta" in e for e in report.errors)

    def test_sample_mode_accepts_a_one_minute_opening(self, settings, tmp_path) -> None:
        #  A amostra de ~60 s para comparar com as entregas: um bloco, 150 palavras.
        files = session_files(words=150, blocks=1)
        files["relatorio_fatos.json"]["itens"][1]["bloco"] = 0
        folder = write_session(tmp_path / "s", files)
        strict = _import(settings, folder, ArtifactStore("v"), validate_only=True)
        assert not strict.ok
        sample = _import(settings, folder, ArtifactStore("v"), validate_only=True, sample=True)
        assert sample.ok, sample.errors
        assert any("fora da meta" in w for w in sample.warnings)
        assert any("3 capitulos" in w for w in sample.warnings)

    def test_a_long_screen_title_is_a_warning(self, settings, tmp_path) -> None:
        files = session_files()
        files["roteiro.pt-br.json"]["blocos"][0]["titulo"] = (
            "O que cabe na mao de um soldado romano"
        )
        files["roteiro.pt-br.json"]["blocos"][1]["titulo"] = "Antes do sol: desmontar o mundo"
        report = _import(settings, write_session(tmp_path / "s", files), ArtifactStore("v"))
        assert report.ok, report.errors
        titles = [w for w in report.warnings if "titulo na tela" in w]
        assert len(titles) == 1 and "bloco 0" in titles[0]

    def test_low_confidence_is_a_warning_the_gate_will_block(self, settings, tmp_path) -> None:
        files = session_files()
        files["relatorio_fatos.json"]["itens"][1]["confianca"] = "baixa"
        report = _import(settings, write_session(tmp_path / "s", files), ArtifactStore("v"))
        assert report.ok
        assert report.gate["aprovado"] is False
        assert any("gate de fatos vai bloquear" in w for w in report.warnings)


def test_english_adaptation_follows_the_script_length() -> None:
    #  Uma amostra de um minuto nao pode voltar do LLM com vinte.
    from mundoantigo.pipeline.steps.s05_adaptacao_en import AdaptacaoEnStep

    short = {"blocos": [{"narracao": "palavra " * 150}]}
    assert AdaptacaoEnStep._target_minutes(short, 150) == (0.9, 1.1)
    full = {"blocos": [{"narracao": "palavra " * 1500}, {"narracao": "palavra " * 1500}]}
    assert AdaptacaoEnStep._target_minutes(full, 150) == (18.0, 22.0)


def test_english_adaptation_output_budget_grows_with_the_script() -> None:
    #  Com 12000 fixos, o roteiro de 20 min voltou cortado (04/10).
    from mundoantigo.pipeline.steps.s05_adaptacao_en import (
        OUTPUT_TOKENS_MAX,
        OUTPUT_TOKENS_MIN,
        AdaptacaoEnStep,
    )

    assert AdaptacaoEnStep._output_budget("x" * 4000) == OUTPUT_TOKENS_MIN
    twenty_minutes = AdaptacaoEnStep._output_budget("palavra " * 5000)
    assert OUTPUT_TOKENS_MIN < twenty_minutes <= OUTPUT_TOKENS_MAX
    assert AdaptacaoEnStep._output_budget("x" * 1_000_000) == OUTPUT_TOKENS_MAX


def test_import_writes_the_step_outputs(settings, tmp_path) -> None:
    folder = write_session(tmp_path / "s", session_files())
    store = ArtifactStore("v-import")
    report = _import(settings, folder, store)
    assert report.ok
    roteiro = store.read_json("roteiro", "roteiro.pt-br.json")
    assert roteiro["palavras_total"] == report.words
    sidecar = store.read_sidecar(store.path("pesquisa", "dossie.json"))
    assert sidecar is not None and sidecar.provider == "claude-code"


class TestSessionMode:
    @pytest.fixture
    def runner(self, settings, recorder, sessions, com_remotion) -> Runner:
        session_settings = dataclasses.replace(
            settings, app={**settings.app, "roteiro": {"modo": "sessao"}}
        )
        llm = FakeLLM(costs=recorder, responses=responder())
        return Runner.build(
            settings=session_settings,
            providers=fake_registry(session_settings, recorder, llm=llm),
            session_factory=sessions,
        )

    async def test_waits_for_the_session_then_runs(
        self, runner, settings, sessions, recorder, tmp_path
    ) -> None:
        video_id = runner.queue.enqueue_video("Um dia na vida de um legionário")
        await Worker(runner, poll_seconds=0).drain(limit=10)
        with sessions() as s:
            steps = {st.name: st.state for st in s.get(Video, video_id).steps}
        assert steps["pesquisa"] is StepState.BLOCKED
        assert not recorder.breakdown_by_step() or all(
            step != "pesquisa" for step, _, _ in recorder.breakdown_by_step()
        ), "o modo sessao nao pode chamar o LLM para pesquisar"

        folder = write_session(tmp_path / "sessao", session_files())
        runner.redo(video_id, [StepName.PESQUISA])
        assert _import(settings, folder, ArtifactStore(video_id)).ok
        await Worker(runner, poll_seconds=0).drain(limit=60)

        with sessions() as s:
            steps = {st.name: st.state for st in s.get(Video, video_id).steps}
        assert steps["pesquisa"] is StepState.SKIPPED
        assert steps["roteiro"] is StepState.SKIPPED
        assert steps["gate_fatos"] is StepState.DONE
        assert steps["revisao"] is StepState.BLOCKED  # chegou ao corte final

    async def test_gate_does_not_rewrite_in_session_mode(
        self, runner, settings, sessions, recorder, tmp_path
    ) -> None:
        video_id = runner.queue.enqueue_video("Tema")
        files = session_files()
        files["relatorio_fatos.json"]["itens"][1]["confianca"] = "baixa"
        _import(settings, write_session(tmp_path / "s", files), ArtifactStore(video_id))
        await Worker(runner, poll_seconds=0).drain(limit=10)

        with sessions() as s:
            video = s.get(Video, video_id)
            steps = {st.name: st.state for st in video.steps}
            reason = video.blocked_reason or ""
        assert steps["gate_fatos"] is StepState.BLOCKED
        assert "corrija na sessao" in reason
        assert all(step != "gate_fatos" for step, _, _ in recorder.breakdown_by_step())
