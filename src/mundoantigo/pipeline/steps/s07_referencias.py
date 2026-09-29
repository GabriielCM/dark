"""Etapa 7: fotos de referencia (Wikimedia Commons, ADR 0006).

Para cenas de lugar, peca e plano detalhe com um alvo real, a etapa busca no
Commons uma foto que sirva de base ao img2img, e guarda autor e licenca para
os creditos da descricao ("Ilustracoes redesenhadas a partir de fotos de
referencia").

Por cena: busca, recusa o que a licenca nao permite (references/licensing.py)
e o que e pequeno demais, compara as melhores com o alvo em miniatura
(references/ranking.py) e baixa so a escolhida. Sem candidata aceita, a cena
sai so do texto, e o motivo fica no indice.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...references.licensing import classify
from ...references.ranking import make_ranker
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

#  Largura padrao do Commons usada so para comparar candidatas.
THUMB_WIDTH = 500


def reference_image(ctx: StepContext, index: int) -> Path:
    return ctx.store.path("referencias", f"cena-{index:03d}.jpg")


class ReferenciasStep(Step):
    name = StepName.REFERENCIAS

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [ctx.store.path("referencias", "indice.json")]

    async def run(self, ctx: StepContext) -> StepResult:
        storyboard = ctx.store.read_json("cenas", "storyboard.json")
        cfg = ctx.settings.app.get("referencias", {})
        wanted = [s for s in storyboard.get("cenas", []) if s.get("referencia")]
        if not wanted:
            ctx.store.write_json("referencias", "indice.json", {"cenas": {}}, step="referencias")
            return StepResult.done(summary="nenhuma cena pede foto de referencia")

        provider = ctx.providers.references()
        ranker = make_ranker(str(cfg.get("ranking", "clip")))
        limit = int(cfg.get("candidatos", 10))
        min_side = int(cfg.get("largura_min", 1024))
        compare = int(cfg.get("comparar", 4))

        index: dict[str, Any] = {"cenas": {}, "ranking": ranker.name}
        found = 0
        for scene in wanted:
            number = int(scene["indice"])
            key = f"{number:03d}"
            target = reference_image(ctx, number)
            if ctx.store.is_complete(target):
                sidecar = ctx.store.read_sidecar(target)
                chosen = sidecar.extra.get("referencia") if sidecar else None
                index["cenas"][key] = {"escolhida": chosen, "reaproveitada": True}
                found += 1
                continue

            reference = scene["referencia"]
            candidates = await provider.search(
                reference["busca"],
                step=self.name.value,
                limit=limit,
                video_id=ctx.video_id,
                step_run_id=ctx.step_run_id,
            )
            evaluated: list[dict[str, Any]] = []
            accepted = []
            for candidate in candidates:
                verdict = classify(candidate.metadata)
                small = max(candidate.width, candidate.height) < min_side
                reason = (
                    verdict.reason if not verdict.accepted else "pequena demais" if small else ""
                )
                evaluated.append(
                    {
                        "curid": candidate.curid,
                        "titulo": candidate.title,
                        "licenca": verdict.license,
                        "aceita": verdict.accepted and not small,
                        "motivo": reason,
                    }
                )
                if verdict.accepted and not small:
                    accepted.append((candidate, verdict))

            if not accepted:
                index["cenas"][key] = {
                    "escolhida": None,
                    "motivo": "nenhuma candidata com licenca aceita e tamanho suficiente",
                    "candidatas": evaluated,
                }
                continue

            shortlist = accepted[:compare]
            thumbs = []
            for candidate, _ in shortlist:
                thumb = ctx.store.path(
                    "referencias", f"candidatas/cena-{key}-{candidate.curid}.jpg"
                )
                await provider.download(candidate, thumb, width=THUMB_WIDTH)
                thumbs.append((thumb, candidate.title))
            scores = ranker.score(thumbs, str(reference["alvo"]))
            for (candidate, _), score in zip(shortlist, scores, strict=True):
                for item in evaluated:
                    if item["curid"] == candidate.curid:
                        item["nota"] = score
            best, verdict = shortlist[max(range(len(scores)), key=scores.__getitem__)]

            await provider.download(best, target)
            provenance = {
                "fonte": "commons",
                "curid": best.curid,
                "titulo": best.title,
                "autor": verdict.author,
                "licenca": verdict.license,
                "licenca_url": verdict.license_url,
                "url": best.page_url,
                "atribuicao_exigida": verdict.attribution_required,
                "verificada": True,
                "busca": reference["busca"],
                "alvo": reference["alvo"],
            }
            ctx.store.write_sidecar(
                target,
                step="referencias",
                provider=getattr(provider, "name", None),
                model=getattr(provider, "model", None),
                extra={"referencia": provenance},
            )
            index["cenas"][key] = {"escolhida": provenance, "candidatas": evaluated}
            found += 1

        ctx.store.write_json("referencias", "indice.json", index, step="referencias")
        return StepResult.done(
            summary=f"{found} de {len(wanted)} cenas com foto de referencia do Commons",
            com_referencia=found,
            pedidas=len(wanted),
        )
