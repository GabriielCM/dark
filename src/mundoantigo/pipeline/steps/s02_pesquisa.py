"""Etapa 2: pesquisa.

Busca web e base de livros; gera um dossie com fontes. Toda afirmacao que
chegar ao roteiro precisa nascer aqui — o roteiro nao inventa fato novo.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...books.kb import KnowledgeBase
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

#  Consultas derivadas do tema. Poucas e especificas: cada uma custa.
QUERY_TEMPLATES = (
    "{tema}",
    "{tema} evidencia arqueologica",
    "{tema} how it worked archaeology",
    "{tema} historians debate",
)


class PesquisaStep(Step):
    name = StepName.PESQUISA

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("pesquisa", "dossie.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        if ctx.script_from_session:
            #  roteiro.modo: sessao. Pesquisa, roteiro e fatos chegam por
            #  `mundoantigo importar-roteiro`; sem eles, espera em vez de pagar.
            return StepResult.blocked(
                f"aguardando a sessao: `mundoantigo importar-roteiro {ctx.video_id} <pasta>`"
            )
        pauta = ctx.store.read_json("pauta", "pauta.json")
        tema = pauta["tema"]

        search = ctx.providers.search()
        hits = []
        seen: set[str] = set()
        for template in QUERY_TEMPLATES:
            query = template.format(tema=tema)
            for hit in await search.search(
                query, step=self.name.value, video_id=ctx.video_id, step_run_id=ctx.step_run_id
            ):
                if hit.url in seen:
                    continue
                seen.add(hit.url)
                hits.append(hit)

        #  Fontes academicas primeiro: o prompt do dossie pesa a ordem.
        hits.sort(key=lambda h: (not h.is_trusted_domain,))

        book_excerpts = self._book_excerpts(ctx, tema)

        prompt_obj = ctx.prompts.get("pesquisa/dossie")
        rendered = prompt_obj.render(
            tema=tema,
            pilar=pauta["pilar"],
            trechos_livros=book_excerpts or "(nenhum livro relevante na base)",
            resultados_busca=json.dumps(
                [
                    {"titulo": h.title, "url": h.url, "trecho": h.snippet, "qualidade": h.quality}
                    for h in hits[:20]
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )

        llm = ctx.providers.llm(fast=prompt_obj.prefers_fast_model)
        response = await llm.complete(
            rendered,
            step=self.name.value,
            video_id=ctx.video_id,
            step_run_id=ctx.step_run_id,
            temperature=0.4,
        )
        dossie = response.json()

        ctx.store.write_json(
            "pesquisa",
            "dossie.json",
            dossie,
            step="pesquisa",
            provider=llm.name,
            model=llm.model,
            prompt_ref=prompt_obj.ref,
            prompt_checksum=prompt_obj.checksum,
        )

        n_sources = len(dossie.get("fontes", []) if isinstance(dossie, dict) else [])
        return StepResult.done(
            summary=f"dossie com {n_sources} fontes ({len(hits)} resultados de busca)",
            fontes=n_sources,
            resultados_busca=len(hits),
        )

    def _book_excerpts(self, ctx: StepContext, tema: str) -> str:
        """Trechos da base de livros. Obra protegida entra so como fonte (brief 4.2)."""
        try:
            kb = KnowledgeBase()
            results = kb.search(tema, limit=8)
        except Exception:
            return ""
        if not results:
            return ""
        return "\n\n".join(
            f"[livro:{r.book_id}#{r.chapter or '?'}] ({r.rights_note})\n{r.text}" for r in results
        )
