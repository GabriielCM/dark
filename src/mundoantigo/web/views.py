"""O que a pagina da producao mostra em cada etapa.

Le os artefatos, nao o estado da fila: uma etapa retomada do disco (pulada
sem gastar) mostra o mesmo que uma que acabou de rodar.
"""

from __future__ import annotations

from typing import Any

from ..artifacts import ArtifactStore
from ..artifacts.jsonfile import read_json_or
from ..clips import Selection
from ..pipeline import StepName
from ..review import final_cut as cut_comments
from ..review import images as review

#  Pasta de artefatos de cada etapa (a etapa e a pasta nem sempre tem o mesmo nome).
STAGE_OF: dict[str, str] = {
    "pauta": "pauta",
    "pesquisa": "pesquisa",
    "roteiro": "roteiro",
    "gate_fatos": "roteiro",
    "adaptacao_en": "adaptacao",
    "narracao": "narracao",
    "cenas": "cenas",
    "referencias": "referencias",
    "assets": "assets",
    "pre_checagem": "pre_checagem",
    "revisao_imagens": "revisao_imagens",
    "trilha": "trilha",
    "metadados": "metadados",
    "montagem": "montagem",
    "cortes": "cortes",
    "revisao": "revisao",
    "entregue": "entrega",
}
#  Pastas grandes demais para listar arquivo por arquivo na pagina.
LIST_LIMIT = 40

#  Etapas cujo corpo e pesado (grade, players): so carregam quando abertas.
HEAVY_STEPS = ("revisao_imagens", "revisao")


def _json(store: ArtifactStore, stage: str, name: str) -> Any:
    return read_json_or(store.path(stage, name), None)


def artifact_files(store: ArtifactStore, step: str) -> list[dict[str, Any]]:
    stage = store.root / STAGE_OF.get(step, step)
    if not stage.is_dir():
        return []
    files = [
        f for f in sorted(stage.iterdir()) if f.is_file() and not f.name.endswith(".meta.json")
    ]
    files = [f for f in files if not f.name.startswith(".") and not f.name.endswith(".lock")]
    return [
        {
            "nome": f.name,
            "tamanho": f.stat().st_size,
            "url": f"/artefatos/{store.video_id}/{stage.name}/{f.name}",
        }
        for f in files[:LIST_LIMIT]
    ] + (
        [{"nome": f"... e mais {len(files) - LIST_LIMIT} arquivo(s)", "tamanho": 0, "url": ""}]
        if len(files) > LIST_LIMIT
        else []
    )


def fact_report(store: ArtifactStore) -> dict[str, Any] | None:
    report = _json(store, "roteiro", "relatorio_fatos.final.json")
    if not isinstance(report, dict):
        return None
    items = report.get("itens", [])
    #  Baixa primeiro, depois media: o revisor le o que importa antes de cansar.
    order = {"baixa": 0, "media": 1, "alta": 2}
    return {
        **report,
        "itens": sorted(items, key=lambda i: order.get(str(i.get("confianca")), 3)),
    }


def _script(store: ArtifactStore) -> dict[str, Any] | None:
    for name in ("roteiro.aprovado.json", "roteiro.pt-br.json"):
        data = _json(store, "roteiro", name)
        if isinstance(data, dict):
            return data
    return None


def _words(text: str) -> int:
    return len(str(text or "").split())


def final_cut(store: ArtifactStore) -> dict[str, Any]:
    """Players, metadados, thumbnails, avisos e relatorio de fatos do corte final."""
    video_id = store.video_id
    dossier = _json(store, "revisao", "revisao.json") or {}
    report = fact_report(store) or {}
    ok, why = cut_comments.can_approve(store)
    videos = {
        lang: f"/artefatos/{video_id}/montagem/video.{lang}.mp4"
        for lang in ("pt-br", "en")
        if store.path("montagem", f"video.{lang}.mp4").exists()
    }
    #  Com a faixa unica nao ha video EN (ADR 0011): a dublagem e conferida
    #  pelo audio, que divide a linha do tempo com o video PT.
    dub = (
        f"/artefatos/{video_id}/narracao/narracao.en.wav"
        if "en" not in videos and store.path("narracao", "narracao.en.wav").exists()
        else None
    )
    return {
        "comentarios": comments_view(store),
        "pode_aprovar": ok,
        "motivo_nao_aprova": why,
        "videos": videos,
        "faixa_en": dub,
        "metadados": {
            lang: data
            for lang in ("pt-br", "en")
            if isinstance(data := _json(store, "metadados", f"metadados.{lang}.json"), dict)
        },
        "thumbnails": {
            label: f"/artefatos/{video_id}/metadados/{name}"
            for label, name in (
                ("PT-BR, com texto", "thumb-com-texto.pt-br.jpg"),
                ("EN, com texto", "thumb-com-texto.en.jpg"),
                ("Sem texto", "thumb-sem-texto.jpg"),
            )
            if store.path("metadados", name).exists()
        },
        "avisos": dossier.get("avisos", []),
        "relatorio": report,
        "tiktok": clips_view(store),
        #  Sem `assets`: refazer dali apagava as 222 imagens. Imagem errada
        #  no corte vira comentario, e a sessao refaz so a imagem.
        "etapas_refazer": [
            StepName.ROTEIRO.value,
            StepName.NARRACAO.value,
            StepName.CENAS.value,
            StepName.METADADOS.value,
            StepName.CORTES.value,
        ],
    }


def clips_view(store: ArtifactStore) -> dict[str, Any]:
    """Os cortes do TikTok de cada idioma (ADR 0010): player, gancho e legenda."""
    raw = _json(store, "cortes", "selecao.json")
    if not isinstance(raw, dict):
        return {"idiomas": {}, "video_inteiro": {}}
    selection = Selection.from_dict(raw)
    languages: dict[str, list[dict[str, Any]]] = {}
    for lang in ("pt-br", "en"):
        items = []
        for clip in selection.clips:
            name = f"corte-{clip.number}.{lang}.mp4"
            if not store.path("cortes", name).exists():
                continue
            items.append(
                {
                    "numero": clip.number,
                    "url": f"/artefatos/{store.video_id}/cortes/{name}",
                    "capitulo": clip.candidate.title,
                    "duracao_s": clip.candidate.span(lang).duration,
                    "gancho": clip.hook[lang],
                    "legenda": clip.caption[lang],
                    "hashtags": clip.hashtags[lang],
                }
            )
        if items:
            languages[lang] = items
    return {"idiomas": languages, "video_inteiro": selection.full_video}


def comments_view(store: ArtifactStore) -> dict[str, Any]:
    """Comentarios do corte: os abertos primeiro, os resolvidos num bloco recolhido."""
    items = cut_comments.load(store)
    return {
        "rascunhos": [c for c in items if c.get("estado") == "rascunho"],
        "enviados": [c for c in items if c.get("estado") == "pendente"],
        "resolvidos": [c for c in items if c.get("estado") in ("resolvido", "descartado")],
    }


def approval_hint(ok: bool, why: str, *, blocked: bool) -> str:
    """Por que o botao "Aprovar todas" esta desligado, em uma frase."""
    if not ok:
        return why
    return "" if blocked else "a grade ainda nao esta pronta"


def image_grid(store: ArtifactStore, step: dict[str, Any] | None) -> dict[str, Any]:
    sections = review.sections(store)
    ok, why = review.can_approve(store)
    blocked = bool(step and step.get("estado") == "blocked")
    states = [i["estado"] for s in sections for i in s["itens"]]
    return {
        "secoes": sections,
        "pode_aprovar": ok and blocked,
        "motivo_nao_aprova": why
        if not ok
        else ("" if blocked else "a grade ainda nao esta pronta"),
        "aguardando": sum(
            1 for st in states if st in ("enviado", "aguardando_claude", "pronto_para_refazer")
        ),
        "refazendo": sum(1 for st in states if st == "refazendo"),
        "total": len(states),
    }


def step_details(store: ArtifactStore, name: str, step: dict[str, Any] | None) -> dict[str, Any]:
    """Os dados do corpo de uma etapa na pagina."""
    data: dict[str, Any] = {"arquivos": artifact_files(store, name)}
    if name == "pauta":
        data["pauta"] = _json(store, "pauta", "pauta.json")
    elif name == "pesquisa":
        dossier = _json(store, "pesquisa", "dossie.json")
        if isinstance(dossier, dict):
            data["dossie"] = {
                "resumo": dossier.get("resumo"),
                "angulo": dossier.get("angulo"),
                "blocos": len(dossier.get("blocos", [])),
                "afirmacoes": sum(len(b.get("afirmacoes", [])) for b in dossier.get("blocos", [])),
                "fontes": len(dossier.get("fontes", [])),
                "lacunas": dossier.get("lacunas", []),
            }
    elif name == "roteiro":
        script = _script(store)
        if script:
            chapters = [
                {"titulo": b.get("titulo"), "palavras": _words(b.get("narracao", ""))}
                for b in script.get("blocos", [])
            ]
            data["roteiro"] = {
                "titulo": script.get("titulo_provisorio"),
                "capitulos": chapters,
                "palavras": sum(c["palavras"] for c in chapters),
            }
    elif name == "gate_fatos":
        data["relatorio"] = fact_report(store)
    elif name == "adaptacao_en":
        script = _json(store, "adaptacao", "roteiro.en.json")
        if isinstance(script, dict):
            data["adaptacao"] = {
                "titulo": script.get("titulo_provisorio"),
                "palavras": sum(_words(b.get("narracao", "")) for b in script.get("blocos", [])),
                "capitulos": [b.get("titulo") for b in script.get("blocos", [])],
            }
    elif name == "cenas":
        board = _json(store, "cenas", "storyboard.json")
        if isinstance(board, dict):
            scenes = board.get("cenas", [])
            kinds: dict[str, int] = {}
            for scene in scenes:
                kinds[str(scene.get("tipo"))] = kinds.get(str(scene.get("tipo")), 0) + 1
            data["storyboard"] = {
                "cenas": len(scenes),
                "duracao_s": board.get("duracao_total_s"),
                "media_s": round(board.get("duracao_total_s", 0) / max(len(scenes), 1), 1),
                "tipos": sorted(kinds.items(), key=lambda kv: -kv[1]),
                "ambientacao": board.get("ambientacao"),
            }
    elif name == "pre_checagem":
        data["pre_checagem"] = _json(store, "pre_checagem", "relatorio.json")
    elif name == "revisao_imagens":
        data["grade"] = image_grid(store, step)
    elif name == "metadados" or name in ("montagem", "revisao"):
        data["corte"] = final_cut(store)
    elif name == "cortes":
        data["tiktok"] = clips_view(store)
        data["avisos_cortes"] = (_json(store, "cortes", "selecao.json") or {}).get("avisos", [])
    elif name == "entregue":
        folder = store.root / "entrega"
        data["entrega"] = str(folder.resolve()) if folder.is_dir() else None
    return data
