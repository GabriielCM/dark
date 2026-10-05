"""Etapa 8: fotos de referencia (Wikimedia Commons, ADR 0006).

Para cenas de lugar, peca e plano detalhe com um alvo real, a etapa busca no
Commons uma foto que sirva de base ao img2img, e guarda autor e licenca para
os creditos da descricao ("Ilustracoes redesenhadas a partir de fotos de
referencia").

Por cena: busca, recusa o que a licenca nao permite (references/licensing.py)
e o que e pequeno demais, compara as melhores com o alvo em miniatura
(references/ranking.py) e baixa so a escolhida. Sem candidata aceita, a cena
sai so do texto, e o motivo fica no indice.

Em lugar e plano detalhe a foto vira a planta da imagem (img2img a 0,75), e
na amostra de 29/09 uma panoramica de museu com uma tuba e uma plaquinha
virou uma cena de torre palida. Nesses tipos tambem sai:
- a foto com proporcao ruim para 16:9 (o recorte central perde o assunto);
- a foto que o CLIP acha mais parecida com uma vitrine, um rotulo ou um
  objeto na parede do que com o alvo (`sondas_descarte`).
A peca e recortada sobre fundo branco antes do img2img: nao passa por isso.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...references.licensing import classify
from ...references.ranking import Ranker, make_ranker
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step

#  Largura padrao do Commons usada so para comparar candidatas.
THUMB_WIDTH = 500
#  Tipos em que a foto inteira vira a planta da imagem.
LAYOUT_KINDS = ("lugar", "plano_detalhe")


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
        ratio_min, ratio_max = (float(v) for v in cfg.get("proporcao", (1.0, 2.4)))
        probes = [str(p) for p in cfg.get("sondas_descarte", ())]

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
            if not reference.get("busca"):
                #  Foto colada pelo revisor na grade (sem busca): so existe o
                #  arquivo que ela trouxe, e ele sumiu. A cena sai sem foto.
                index["cenas"][key] = {"escolhida": None, "motivo": "foto do revisor ausente"}
                continue
            candidates = await provider.search(
                reference["busca"],
                step=self.name.value,
                limit=limit,
                video_id=ctx.video_id,
                step_run_id=ctx.step_run_id,
            )
            layout = str(scene.get("tipo") or "") in LAYOUT_KINDS
            evaluated: list[dict[str, Any]] = []
            accepted = []
            for candidate in candidates:
                verdict = classify(candidate.metadata)
                reason = ""
                if not verdict.accepted:
                    reason = verdict.reason
                elif max(candidate.width, candidate.height) < min_side:
                    reason = "pequena demais"
                elif layout and not (
                    ratio_min <= candidate.width / max(candidate.height, 1) <= ratio_max
                ):
                    reason = "proporcao ruim para 16:9"
                evaluated.append(
                    {
                        "curid": candidate.curid,
                        "titulo": candidate.title,
                        "licenca": verdict.license,
                        "aceita": not reason,
                        "motivo": reason,
                    }
                )
                if not reason:
                    accepted.append((candidate, verdict))

            if not accepted:
                index["cenas"][key] = {
                    "escolhida": None,
                    "motivo": "nenhuma candidata com licenca, tamanho e proporcao aceitos",
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
            scores, rejected = self._rank(
                ranker, thumbs, str(reference["alvo"]), probes if layout else []
            )
            by_curid = {item["curid"]: item for item in evaluated}
            for (candidate, _), score, probe in zip(shortlist, scores, rejected, strict=True):
                item = by_curid[candidate.curid]
                item["nota"] = score
                if probe:
                    item["aceita"] = False
                    item["motivo"] = f"parece mais {probe!r} do que o alvo"
            kept = [i for i, probe in enumerate(rejected) if not probe]
            if not kept:
                index["cenas"][key] = {
                    "escolhida": None,
                    "motivo": "as candidatas parecem vitrine, rotulo ou objeto, nao o alvo",
                    "candidatas": evaluated,
                }
                continue
            best, verdict = shortlist[max(kept, key=scores.__getitem__)]

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

    @staticmethod
    def _rank(
        ranker: Ranker, thumbs: list[tuple[Path, str]], target: str, probes: list[str]
    ) -> tuple[list[float], list[str | None]]:
        """Nota de cada candidata contra o alvo e a sonda que ganhou dele, se alguma.

        Sem sondas, ou com um ranking que nao compara texto com imagem (o pelo
        titulo), so a nota.
        """
        score_texts = getattr(ranker, "score_texts", None)
        if not probes or score_texts is None:
            scores = ranker.score(thumbs, target)
            return scores, [None] * len(scores)
        matrix = score_texts(thumbs, [target, *probes])
        scores = [row[0] for row in matrix]
        rejected: list[str | None] = []
        for row in matrix:
            best = max(range(1, len(row)), key=row.__getitem__)
            rejected.append(probes[best - 1] if row[best] > row[0] else None)
        return scores, rejected
