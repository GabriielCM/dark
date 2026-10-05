"""Comandos das revisoes humanas usados pela sessao do Claude Code.

O revisor trabalha na pagina da producao. A sessao trabalha por aqui: le os
pedidos de refacao que precisam dela, reescreve descricoes e aplica.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from .artifacts import ArtifactStore
from .db.models import StepState, Video
from .pipeline import StepName
from .review import images as review


def _store(video_id: str) -> ArtifactStore:
    store = ArtifactStore(video_id)
    if not store.root.exists():
        raise ValueError(f"producao {video_id} nao existe")
    return store


def _image_steps_busy(runner: Any, video_id: str) -> bool:
    with runner.session_factory() as s:
        video = s.get(Video, video_id)
        if video is None:
            raise ValueError(f"producao {video_id} nao existe")
        states = {st.name: st.state for st in video.steps}
    busy = (StepName.ASSETS.value, StepName.PRE_CHECAGEM.value)
    return any(states.get(name) is StepState.RUNNING for name in busy)


def cmd_imagens_pedidos(args: argparse.Namespace) -> int:
    store = _store(args.video_id)
    requests = review.load_requests(store) if args.todos else review.claude_pending(store)
    items = {item["chave"]: item for item in review.grid(store)}
    out: list[dict[str, Any]] = []
    for entry in requests:
        item = items.get(str(entry.get("alvo")), {})
        out.append(
            {
                **entry,
                "imagem_absoluta": str((store.root / item["imagem"]).resolve()) if item else None,
                "descricao_atual": item.get("descricao"),
                "narracao": item.get("narracao"),
                "capitulo": item.get("capitulo"),
                "tipo_cena": item.get("tipo"),
            }
        )
    if not args.nao_marcar:
        review.mark_seen(store)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not out:
        print("nenhum pedido esperando a sessao")
        return 0
    for entry in out:
        print(f"#{entry['id']} {entry['alvo']} [{entry.get('estado')}] ({entry.get('capitulo')})")
        if entry.get("motivo"):
            print(f"  motivo: {entry['motivo']}")
        if entry.get("link"):
            print(f"  link: {entry['link']}")
        print(f"  narracao: {(entry.get('narracao') or '')[:160]}")
        print(f"  descricao atual: {entry.get('descricao_atual')}")
        print(f"  imagem: {entry.get('imagem_absoluta')}")
    return 0


def cmd_imagens_descrever(args: argparse.Namespace) -> int:
    entry = review.describe(
        _store(args.video_id),
        args.chave,
        args.descricao,
        request_id=args.pedido,
        reply=args.resposta,
    )
    print(f"{entry['alvo']}: descricao nova pronta (pedido #{entry['id']}); rode `imagens aplicar`")
    return 0


def cmd_imagens_refazer(args: argparse.Namespace) -> int:
    entry = review.redo_without_change(
        _store(args.video_id), args.chave, request_id=args.pedido, reply=args.resposta
    )
    print(f"{entry['alvo']}: refacao com semente nova pronta (pedido #{entry['id']})")
    return 0


def cmd_imagens_recusar(args: argparse.Namespace) -> int:
    entry = review.refuse(_store(args.video_id), args.pedido, args.resposta)
    print(f"pedido #{entry['id']} ({entry['alvo']}) recusado")
    return 0


def cmd_imagens_aplicar(args: argparse.Namespace) -> int:
    from .cli import _runner

    runner = _runner()
    store = _store(args.video_id)
    if _image_steps_busy(runner, args.video_id):
        print("a etapa de imagens esta rodando: o worker aplica os pedidos assim que ela terminar")
        return 0
    report = asyncio.run(review.apply(store, runner.providers.references()))
    for key, detail in report.refused:
        print(f"  {key}: recusado ({detail})")
    if report.changed:
        runner.redo_images(args.video_id)
        print(f"{len(report.applied)} imagem(ns) de volta a fila: {', '.join(report.applied)}")
    elif not report.refused:
        print("nenhum pedido pronto para aplicar")
    return 0


def register(sub: Any) -> None:
    p = sub.add_parser("imagens", help="pedidos de refacao da grade de imagens (sessao)")
    imagens = p.add_subparsers(dest="acao", required=True)

    q = imagens.add_parser("pedidos", help="pedidos que esperam a sessao do Claude")
    q.add_argument("video_id")
    q.add_argument("--json", action="store_true")
    q.add_argument("--todos", action="store_true", help="todos os pedidos, de qualquer estado")
    q.add_argument(
        "--nao-marcar", action="store_true", help="nao marca como visto pelo Claude na pagina"
    )
    q.set_defaults(func=cmd_imagens_pedidos)

    q = imagens.add_parser("descrever", help="reescreve a descricao de uma imagem a refazer")
    q.add_argument("video_id")
    q.add_argument("chave", help="cena-012, cena-012-peca-2 ou thumb")
    q.add_argument("descricao", help="descricao nova, em ingles")
    q.add_argument("--pedido", type=int, help="pedido do revisor que esta sendo atendido")
    q.add_argument("--resposta", help="o que mudou, mostrado ao revisor na pagina")
    q.set_defaults(func=cmd_imagens_descrever)

    q = imagens.add_parser("refazer", help="refaz com semente nova e a mesma descricao")
    q.add_argument("video_id")
    q.add_argument("chave", help="cena-012, thumb ou mc-<pose>")
    q.add_argument("--pedido", type=int)
    q.add_argument("--resposta")
    q.set_defaults(func=cmd_imagens_refazer)

    q = imagens.add_parser("recusar", help="nao refaz: explica o porque ao revisor")
    q.add_argument("video_id")
    q.add_argument("pedido", type=int)
    q.add_argument("resposta")
    q.set_defaults(func=cmd_imagens_recusar)

    q = imagens.add_parser("aplicar", help="aplica os pedidos prontos e devolve as imagens a fila")
    q.add_argument("video_id")
    q.set_defaults(func=cmd_imagens_aplicar)
