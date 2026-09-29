"""Teste de ponta a ponta barato.

CLAUDE.md pede "um video-exemplo de cerca de 60 s como teste de ponta a ponta".
Roda o pipeline inteiro com provedores falsos: sem rede, sem GPU, sem gasto.
"""

from __future__ import annotations

import json

import pytest

from mundoantigo.artifacts import ArtifactStore
from mundoantigo.db.models import FactItem, StepState, Video, VideoState
from mundoantigo.pipeline import Runner, StepName, Worker, video_progress
from mundoantigo.providers import fake_registry
from mundoantigo.providers.llm import FakeLLM

from .fakes import responder


@pytest.fixture
def runner(settings, recorder, sessions, sem_remotion):
    llm = FakeLLM(costs=recorder, responses=responder())
    providers = fake_registry(settings, recorder, llm=llm)
    runner = Runner.build(settings=settings, providers=providers, session_factory=sessions)
    runner.llm = llm  # type: ignore[attr-defined]
    return runner


async def drain(runner: Runner, limit: int = 40) -> int:
    return await Worker(runner, poll_seconds=0).drain(limit=limit)


class TestFullRun:
    async def test_pipeline_reaches_review(self, runner, sessions) -> None:
        """Sem Remotion instalado, a producao para na montagem — com as props prontas."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos", pillar="engenharia")
        await drain(runner)

        progress = video_progress(sessions, video_id)
        by_name = {s["nome"]: s for s in progress["etapas"]}

        for step in (
            "pauta",
            "pesquisa",
            "roteiro",
            "gate_fatos",
            "adaptacao_en",
            "cenas",
            "assets",
            "narracao",
        ):
            assert by_name[step]["estado"] == "done", f"{step}: {by_name[step]}"

        #  A montagem bloqueia porque o projeto Node nao esta instalado no CI.
        assert by_name["montagem"]["estado"] == "blocked"
        assert "Remotion" in (by_name["montagem"]["resumo"] or "")

        store = ArtifactStore(video_id)
        for lang in ("pt-br", "en"):
            assert store.path("montagem", f"props.{lang}.json").exists()

    async def test_all_expected_artifacts_exist(self, runner) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        esperados = [
            ("pauta", "pauta.json"),
            ("pesquisa", "dossie.json"),
            ("roteiro", "roteiro.pt-br.json"),
            ("roteiro", "relatorio_fatos.json"),
            ("roteiro", "roteiro.aprovado.json"),
            ("roteiro", "relatorio_fatos.final.json"),
            ("adaptacao", "roteiro.en.json"),
            ("cenas", "storyboard.json"),
            ("narracao", "narracao.pt-br.wav"),
            ("narracao", "narracao.en.wav"),
            ("narracao", "legendas.pt-br.srt"),
            ("narracao", "legendas.en.srt"),
        ]
        for stage, filename in esperados:
            path = store.path(stage, filename)
            assert path.exists(), f"faltou {stage}/{filename}"
            assert store.is_complete(path), f"sidecar ausente em {stage}/{filename}"

    async def test_every_artifact_has_traceability_sidecar(self, runner) -> None:
        """CLAUDE.md, rastreabilidade: modelo, provedor, versao do prompt, data."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        sidecar = store.read_sidecar(store.path("pesquisa", "dossie.json"))
        assert sidecar is not None
        assert sidecar.provider == "fake"
        assert sidecar.prompt_ref == "pesquisa/dossie@v1"
        assert sidecar.prompt_checksum
        assert sidecar.created_at

        #  Cenarios guardam a semente: e o que permite reproduzir a imagem.
        cena = store.read_sidecar(store.path("assets", "cena-001.png"))
        assert cena is not None and cena.seed is not None

    async def test_srt_generated_for_both_languages(self, runner) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        for lang in ("pt-br", "en"):
            srt = store.read_text("narracao", f"legendas.{lang}.srt")
            assert "-->" in srt
            assert srt.startswith("1\n")

    async def test_scenes_match_storyboard(self, runner) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        storyboard = store.read_json("cenas", "storyboard.json")
        for scene in storyboard["cenas"]:
            index = scene["indice"]
            if scene["tipo"] == "cartao":
                #  Cartao explicativo: pecas recortadas no lugar do cenario.
                assert store.path("assets", f"cena-{index:03d}-peca-1.png").exists()
            else:
                assert store.path("assets", f"cena-{index:03d}.png").exists()

    async def test_props_contract_is_valid(self, runner) -> None:
        from mundoantigo.render import VideoProps

        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        store = ArtifactStore(video_id)

        raw = json.loads(store.path("montagem", "props.pt-br.json").read_text())
        props = VideoProps.model_validate(raw)
        assert props.scenes
        assert props.durationInSeconds > 0
        assert props.duration_in_frames == round(props.durationInSeconds * props.fps)
        #  Cenas cobrem o video sem buraco entre elas.
        for anterior, seguinte in zip(props.scenes, props.scenes[1:], strict=False):
            assert seguinte.start == pytest.approx(anterior.start + anterior.duration, abs=0.01)

    async def test_cost_is_recorded_per_step(self, runner, recorder) -> None:
        runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        steps = {s for s, _, _ in recorder.breakdown_by_step()}
        assert {"pesquisa", "roteiro", "cenas", "assets", "narracao"} <= steps


class TestFactGateInPipeline:
    async def test_gate_rewrites_and_proceeds(
        self, settings, recorder, sessions, sem_remotion
    ) -> None:
        """Reescrita automatica resolve e o pipeline segue (brief 3.4)."""
        llm = FakeLLM(costs=recorder, responses=responder(gate_reprova_uma_vez=True))
        runner = Runner.build(
            settings=settings,
            providers=fake_registry(settings, recorder, llm=llm),
            session_factory=sessions,
        )
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        store = ArtifactStore(video_id)
        report = store.read_json("roteiro", "relatorio_fatos.final.json")
        assert report["aprovado"] is True
        assert report["reescritas"] == 1
        assert store.path("roteiro", "roteiro.aprovado.json").exists()

    async def test_gate_blocks_when_rewrites_do_not_help(
        self, settings, recorder, sessions, sem_remotion
    ) -> None:
        """Nenhuma renderizacao sem gate aprovado (CLAUDE.md)."""
        from .fakes import DOSSIE, NARRACAO_PT, RELATORIO_REPROVADO, _roteiro

        def sempre_reprova(prompt: str) -> str:
            if "Monte um dossiê" in prompt:
                return json.dumps(DOSSIE, ensure_ascii=False)
            if "verificador de fatos" in prompt:
                return json.dumps(RELATORIO_REPROVADO, ensure_ascii=False)
            if "roteiros de documentário" in prompt:
                return json.dumps(_roteiro(NARRACAO_PT, "t"), ensure_ascii=False)
            return json.dumps({"correcoes": []}, ensure_ascii=False)

        llm = FakeLLM(costs=recorder, responses=sempre_reprova)
        runner = Runner.build(
            settings=settings,
            providers=fake_registry(settings, recorder, llm=llm),
            session_factory=sessions,
        )
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        store = ArtifactStore(video_id)
        assert not store.path("roteiro", "roteiro.aprovado.json").exists()
        assert not store.path("adaptacao", "roteiro.en.json").exists()
        assert not store.path("narracao", "narracao.pt-br.wav").exists()

        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.state is VideoState.GATE_FATOS
            assert "gate de fatos" in (video.blocked_reason or "")

    async def test_fact_items_are_persisted(self, runner, sessions) -> None:
        """O painel precisa do relatorio sem abrir arquivo."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        with sessions() as s:
            items = s.query(FactItem).filter(FactItem.video_id == video_id).all()
        assert len(items) >= 2
        assert all(i.claim for i in items)


class TestResume:
    """A promessa central do ADR 0002, verificada de ponta a ponta."""

    async def test_resume_does_not_repeat_paid_calls(self, runner, recorder) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        chamadas_antes = sum(n for _, _, n in recorder.breakdown_by_step())
        assert chamadas_antes > 0

        #  Reenfileira tudo sem apagar nada: e o cenario "o processo caiu".
        runner.queue.reset_step(video_id, StepName.PAUTA)
        await drain(runner)

        chamadas_depois = sum(n for _, _, n in recorder.breakdown_by_step())
        assert chamadas_depois == chamadas_antes, "a retomada repetiu chamadas pagas"

    async def test_resumed_steps_are_marked_skipped(self, runner, sessions) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)
        runner.queue.reset_step(video_id, StepName.PAUTA)
        await drain(runner)

        with sessions() as s:
            video = s.get(Video, video_id)
            skipped = [st.name for st in video.steps if st.state is StepState.SKIPPED]
        assert "pauta" in skipped
        assert "roteiro" in skipped

    async def test_deleting_a_stage_forces_that_stage_only(self, runner, recorder) -> None:
        """Apagar um diretorio e a interface de 'refazer' (ADR 0002)."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        antes = {s: n for s, _, n in recorder.breakdown_by_step()}
        ArtifactStore(video_id).clear_stage("assets")
        runner.queue.reset_step(video_id, StepName.ASSETS)
        await drain(runner)

        depois = {s: n for s, _, n in recorder.breakdown_by_step()}
        assert depois["assets"] == antes["assets"] * 2, "os cenarios nao foram refeitos"
        assert depois["roteiro"] == antes["roteiro"], "o roteiro foi refeito a toa"

    async def test_partial_assets_only_fills_the_gaps(self, runner, recorder) -> None:
        """Falhar na cena 87 nao pode refazer as 86 anteriores."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        store = ArtifactStore(video_id)
        antes = {s: n for s, _, n in recorder.breakdown_by_step()}
        cenas = store.read_json("cenas", "storyboard.json")["cenas"]
        com_cenario = [c["indice"] for c in cenas if c["tipo"] != "cartao"]

        #  Apaga so duas cenas, como se elas tivessem falhado.
        for indice in (2, 5):
            store.path("assets", f"cena-{indice:03d}.png").unlink()

        runner.queue.reset_step(video_id, StepName.ASSETS)
        await drain(runner)

        depois = {s: n for s, _, n in recorder.breakdown_by_step()}
        geradas = depois["assets"] - antes["assets"]
        assert geradas == 2, f"gerou {geradas} imagens em vez das 2 que faltavam"
        assert all(store.path("assets", f"cena-{i:03d}.png").exists() for i in com_cenario)


class TestApproval:
    async def test_approve_completes_the_delivery(self, runner, sessions) -> None:
        """Aprovar destrava a entrega e gera o pacote."""
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        #  A montagem bloqueou por falta do Remotion; simula os videos prontos
        #  para exercitar revisao e entrega.
        store = ArtifactStore(video_id)
        for lang in ("pt-br", "en"):
            video_file = store.path("montagem", f"video.{lang}.mp4")
            video_file.write_bytes(b"\x00" * 2048)
            store.write_sidecar(video_file, step="montagem", provider="remotion")
        runner.queue.unblock(video_id, StepName.MONTAGEM)
        await drain(runner)

        with sessions() as s:
            assert s.get(Video, video_id).state is VideoState.REVISAO

        runner.approve(video_id, reviewer="teste")
        await drain(runner)

        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.state is VideoState.ENTREGUE
            assert video.reviewed_at is not None

        pacote = store.read_json("entrega", "pacote.json")
        assert pacote["idiomas"]["pt-br"]["titulo"]
        assert "custo_usd" in pacote
        checklist = store.read_text("entrega", "CHECKLIST.md")
        assert "Conteúdo alterado ou sintético" in checklist

    async def test_reject_records_reason_and_requeues(self, runner, sessions) -> None:
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        runner.reject(video_id, "o gancho esta fraco", redo_from=StepName.ROTEIRO)

        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.review_rejection_reason == "o gancho esta fraco"
            estados = {st.name: st.state for st in video.steps}
        assert estados["roteiro"] is StepState.PENDING
        assert estados["pauta"] is StepState.DONE

        store = ArtifactStore(video_id)
        rejeicao = store.read_json("revisao", "rejeicao.json")
        assert rejeicao["motivo"] == "o gancho esta fraco"
        assert rejeicao["refazer_a_partir_de"] == "roteiro"
        #  Rejeitar refaz de verdade: o roteiro some, a pesquisa (antes dele) fica.
        assert not store.path("roteiro", "roteiro.pt-br.json").exists()
        assert store.path("pesquisa", "dossie.json").exists()
        historico = store.read_json("revisao", "rejeicoes.json")
        assert historico[-1]["motivo"] == "o gancho esta fraco"


class TestBudgetInPipeline:
    async def test_budget_cap_blocks_instead_of_failing(
        self, settings, prices, sessions, sem_remotion
    ) -> None:
        """Teto atingido bloqueia a producao; nao a mata (ADR 0003)."""
        from mundoantigo.config import BudgetConfig
        from mundoantigo.costs import CostRecorder

        apertado = BudgetConfig(
            soft_limit_usd=0.0,
            hard_limit_usd=0.0001,
            per_video_limit_usd=0.0001,
            unknown_model="strict",
        )
        recorder = CostRecorder(apertado, prices, sessions)
        #  Provedor pago de verdade na tabela de precos, para o teto morder.
        llm = FakeLLM(costs=recorder, responses=responder())
        llm.model = "anthropic/claude-sonnet-5"
        llm.name = "openrouter"

        runner = Runner.build(
            settings=settings,
            providers=fake_registry(settings, recorder, llm=llm),
            session_factory=sessions,
        )
        video_id = runner.queue.enqueue_video("Aquedutos romanos")
        await drain(runner)

        with sessions() as s:
            video = s.get(Video, video_id)
            assert video.state is not VideoState.ENTREGUE
            assert "orcamento" in (video.blocked_reason or "").lower()
            estados = {st.name: st.state for st in video.steps}
        #  Bloqueada, nao falhada: retoma sozinha quando o mes virar.
        assert StepState.FAILED not in estados.values()
        assert StepState.BLOCKED in estados.values()


class TestMontageWhenRemotionIsAvailable:
    """O caminho feliz da montagem, sem pagar os minutos de render de verdade."""

    @pytest.fixture
    def runner_com_render(self, settings, recorder, sessions, com_remotion):
        llm = FakeLLM(costs=recorder, responses=responder())
        return Runner.build(
            settings=settings,
            providers=fake_registry(settings, recorder, llm=llm),
            session_factory=sessions,
        )

    async def test_pipeline_runs_to_review(self, runner_com_render, sessions) -> None:
        video_id = runner_com_render.queue.enqueue_video("Aquedutos romanos")
        await drain(runner_com_render)

        with sessions() as s:
            assert s.get(Video, video_id).state is VideoState.REVISAO

        store = ArtifactStore(video_id)
        for lang in ("pt-br", "en"):
            assert store.path("montagem", f"video.{lang}.mp4").exists()
            assert store.path("metadados", f"metadados.{lang}.json").exists()
            assert store.is_complete(store.path("metadados", f"thumb-com-texto.{lang}.jpg"))
        assert store.is_complete(store.path("metadados", "thumb-sem-texto.jpg"))
        #  A arte base sai com os cenarios, para passar pela revisao de imagens.
        assert store.is_complete(store.path("assets", "thumb-base.png"))

    async def test_review_dossier_lists_the_videos(self, runner_com_render) -> None:
        video_id = runner_com_render.queue.enqueue_video("Aquedutos romanos")
        await drain(runner_com_render)

        dossie = ArtifactStore(video_id).read_json("revisao", "revisao.json")
        assert set(dossie["videos"]) == {"pt-br", "en"}
        assert dossie["relatorio_fatos"]["aprovado"] is True

    async def test_metadata_carries_synthetic_disclosure(self, runner_com_render) -> None:
        """Divulgacao de conteudo sintetico quando aplicavel (brief 7)."""
        video_id = runner_com_render.queue.enqueue_video("Aquedutos romanos")
        await drain(runner_com_render)
        store = ArtifactStore(video_id)

        pt = store.read_json("metadados", "metadados.pt-br.json")
        en = store.read_json("metadados", "metadados.en.json")
        assert "Narração e ilustrações geradas por IA" in pt["descricao"]
        assert "Narration and illustrations generated by AI" in en["descricao"]
        #  As fontes vao na descricao (brief 3.6), no formato "Titulo (ano): link".
        assert "- Roman Aqueducts (2018): https://cambridge.org/aqueducts" in pt["descricao"]
        assert pt["descricao"].index("Fontes:") < pt["descricao"].index("Narração e")
        assert en["descricao"].count("Sources:") == 1

    async def test_chapters_start_at_zero(self, runner_com_render) -> None:
        video_id = runner_com_render.queue.enqueue_video("Aquedutos romanos")
        await drain(runner_com_render)
        metadata = ArtifactStore(video_id).read_json("metadados", "metadados.pt-br.json")
        assert metadata["capitulos"][0]["tempo"] == "00:00"

    async def test_full_delivery_after_approval(self, runner_com_render, sessions) -> None:
        video_id = runner_com_render.queue.enqueue_video("Aquedutos romanos")
        await drain(runner_com_render)
        runner_com_render.approve(video_id, reviewer="teste")
        await drain(runner_com_render)

        with sessions() as s:
            assert s.get(Video, video_id).state is VideoState.ENTREGUE

        store = ArtifactStore(video_id)
        pacote = store.read_json("entrega", "pacote.json")
        for lang in ("pt-br", "en"):
            entry = pacote["idiomas"][lang]
            assert entry["video"] == f"entrega/{lang}/video.mp4"
            assert entry["legendas"] and entry["titulo"] and entry["capitulos"]
            folder = store.root / "entrega" / lang
            for name in ("video.mp4", "legendas.srt", "thumb-com-texto.jpg", "thumb-sem-texto.jpg"):
                assert (folder / name).stat().st_size > 0, name
            publication = (folder / "publicacao.txt").read_text(encoding="utf-8")
            assert entry["titulo"] in publication and "tags" in publication
        #  O video do pacote e o mesmo arquivo da montagem, sem copia.
        linked = store.root / "entrega" / "pt-br" / "video.mp4"
        assert linked.stat().st_ino == store.path("montagem", "video.pt-br.mp4").stat().st_ino
        assert pacote["thumbnail"] == "entrega/thumb-base.png"
        text = store.read_text("entrega", "pacote de entrega.txt")
        assert text.index("português") < text.index("inglês")
        assert "Checklist de publicação" in store.read_text("entrega", "CHECKLIST.md")
