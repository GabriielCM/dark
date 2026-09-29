"""Etapa 4: gate de fatos.

Regra que nao muda sem aprovacao: um item de baixa confianca bloqueia a
renderizacao. A etapa tenta reescrever sozinha o numero configurado de vezes;
se nao resolver, escala para humano em vez de falhar.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ...db.models import Confidence
from ...text.segment import segment_script, units_to_json
from ..context import StepContext, StepResult
from ..fact_gate import FactCheckItem, FactGate
from ..state import StepName
from .base import Step


class GateFatosStep(Step):
    name = StepName.GATE_FATOS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("roteiro", "roteiro.aprovado.json"),
            ctx.store.path("roteiro", "relatorio_fatos.final.json"),
            ctx.store.path("roteiro", "frases.pt-br.json"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        gate = FactGate(ctx.settings.facts)
        roteiro = ctx.store.read_json("roteiro", "roteiro.pt-br.json")
        dossie = ctx.store.read_json("pesquisa", "dossie.json")
        report = ctx.store.read_json("roteiro", "relatorio_fatos.json")

        items = gate.downgrade_unsourced(gate.parse(report))
        verdict = gate.evaluate(items)
        rewrites = 0

        #  Com o roteiro vindo da sessao, a correcao tambem e feita la: a
        #  reescrita automatica pelo OpenRouter e o que o modo sessao evita pagar.
        max_rewrites = 0 if ctx.script_from_session else ctx.settings.facts.max_rewrites
        while not verdict.passed and rewrites < max_rewrites:
            if not verdict.blocking:
                #  Relatorio vazio: reescrever nao resolve, so um humano resolve.
                break
            rewrites += 1
            roteiro, items = await self._rewrite(ctx, gate, roteiro, dossie, verdict.blocking)
            verdict = gate.evaluate(items)

        final_report = {
            "itens": [
                {
                    "id": i.id,
                    "afirmacao": i.claim,
                    "fontes": list(i.sources),
                    "confianca": i.confidence.value,
                    "justificativa": i.justification,
                    "correcao_sugerida": i.suggested_fix,
                    "bloco": i.block_index,
                }
                for i in items
            ],
            "resumo": verdict.counts,
            "reescritas": rewrites,
            "aprovado": verdict.passed,
            "motivo": verdict.reason,
        }
        ctx.store.write_json(
            "roteiro",
            "relatorio_fatos.final.json",
            final_report,
            step="gate_fatos",
            extra={"reescritas": rewrites},
        )
        #  Guardado para o painel mostrar ao lado do corte final, e para o
        #  runner gravar em `facts`.
        ctx.scratch["fact_items"] = items
        ctx.scratch["fact_verdict"] = verdict

        if not verdict.passed:
            fix = (
                "corrija na sessao e reimporte com `mundoantigo importar-roteiro`"
                if ctx.script_from_session
                else f"{rewrites} reescrita(s) automatica(s) nao resolveram"
            )
            return StepResult.blocked(
                f"gate de fatos reprovou: {verdict.reason}. {fix}.",
                bloqueantes=verdict.blocking_count,
                reescritas=rewrites,
                resumo_confianca=verdict.counts,
            )

        #  So grava o roteiro aprovado depois de passar. Enquanto nao passa, o
        #  artefato nao existe — e e a ausencia dele que segura a etapa 5.
        ctx.store.write_json(
            "roteiro",
            "roteiro.aprovado.json",
            roteiro,
            step="gate_fatos",
            extra={"reescritas": rewrites, "resumo_fatos": verdict.counts},
        )
        #  As frases do roteiro aprovado: unidade de tempo de audio, cenas e legendas.
        channel = ctx.channel_pt
        units = segment_script(
            roteiro, prefix="p", language=channel.language, words_per_minute=channel.wpm
        )
        ctx.store.write_json(
            "roteiro", "frases.pt-br.json", units_to_json(units), step="gate_fatos"
        )
        return StepResult.done(
            summary=f"gate aprovado: {verdict.reason}"
            + (f" apos {rewrites} reescrita(s)" if rewrites else ""),
            reescritas=rewrites,
            resumo_confianca=verdict.counts,
        )

    async def _rewrite(
        self,
        ctx: StepContext,
        gate: FactGate,
        roteiro: dict[str, Any],
        dossie: dict[str, Any],
        blocking: tuple[FactCheckItem, ...],
    ) -> tuple[dict[str, Any], list[FactCheckItem]]:
        """Pede correcao dos trechos reprovados e reavalia o roteiro inteiro."""
        prompt_obj = ctx.prompts.get("gate/reescrita")
        rendered = prompt_obj.render(
            roteiro=json.dumps(roteiro, ensure_ascii=False, indent=2),
            itens_baixa=json.dumps(
                [
                    {
                        "id": i.id,
                        "afirmacao": i.claim,
                        "justificativa": i.justification,
                        "correcao_sugerida": i.suggested_fix,
                    }
                    for i in blocking
                ],
                ensure_ascii=False,
                indent=2,
            ),
            dossie=json.dumps(dossie, ensure_ascii=False, indent=2),
        )
        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.3,
        )
        corrections = response.json().get("correcoes", [])
        patched = self._apply(roteiro, corrections)

        #  Reavalia com o mesmo prompt de checagem: uma correcao so vale se o
        #  verificador concordar. Nao acreditamos na palavra de quem corrigiu.
        check_prompt = ctx.prompts.get("roteiro/relatorio_fatos")
        recheck = await llm.complete(
            check_prompt.render(
                roteiro=json.dumps(patched, ensure_ascii=False, indent=2),
                dossie=json.dumps(dossie, ensure_ascii=False, indent=2),
            ),
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.1,
        )
        items = gate.downgrade_unsourced(gate.parse(recheck.json()))
        return patched, items

    @staticmethod
    def _apply(roteiro: dict[str, Any], corrections: list[dict[str, Any]]) -> dict[str, Any]:
        """Aplica as substituicoes de texto nos blocos do roteiro."""
        patched = json.loads(json.dumps(roteiro))  # copia profunda barata
        for correction in corrections:
            action = str(correction.get("acao", "")).lower()
            if action == "escalar":
                continue
            old = str(correction.get("texto_antigo") or "")
            new = str(correction.get("texto_novo") or "")
            if not old:
                continue
            for block in patched.get("blocos", []):
                narration = str(block.get("narracao", ""))
                if old in narration:
                    block["narracao"] = narration.replace(old, new)
                    break
        patched["palavras_total"] = sum(
            len(str(b.get("narracao", "")).split()) for b in patched.get("blocos", [])
        )
        return patched


def summarize_confidences(items: list[FactCheckItem]) -> dict[str, int]:
    counts = {c.value: 0 for c in Confidence}
    for item in items:
        counts[item.confidence.value] += 1
    return counts
