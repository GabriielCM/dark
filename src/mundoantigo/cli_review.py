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
from .config import get_settings
from .db.models import StepState, Video
from .pipeline import StepName
from .review import images as review

#  Codigo de saida de `aguardar` e `respostas --esperar` quando o tempo acaba.
EXIT_TIMEOUT = 3


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


def cmd_imagens_folhas(args: argparse.Namespace) -> int:
    from .review.sheets import contact_sheets

    sheets = contact_sheets(_store(args.video_id), chapter=args.capitulo, per_sheet=args.por_folha)
    if not sheets:
        print("nenhuma imagem para conferir")
        return 1
    for sheet in sheets:
        print(sheet)
    return 0


def _announcer() -> Any:
    from .db.session import get_sessionmaker, init_db
    from .notify import Announcer, build_notifier

    init_db()
    settings = get_settings()
    return Announcer(get_sessionmaker(), build_notifier(settings), settings)


def cmd_perguntar(args: argparse.Namespace) -> int:
    from .conversation import questions

    store = _store(args.video_id)
    entry = questions.ask(
        store,
        args.texto,
        options=args.opcao,
        free_text=not args.sem_texto_livre,
        step=args.etapa,
        target=args.alvo,
    )
    _announcer().announce(
        args.video_id, "pergunta", f"O Claude pergunta: {entry['texto']}", step="perguntas"
    )
    print(entry["id"])
    return 0


def _print_answer(entry: dict[str, Any]) -> None:
    answer = entry.get("resposta") or {}
    parts = [f"#{entry['id']} {entry['texto']}"]
    if answer.get("opcao"):
        parts.append(f"  opcao: {answer['opcao']}")
    if answer.get("texto"):
        parts.append(f"  resposta: {answer['texto']}")
    print("\n".join(parts))


def cmd_respostas(args: argparse.Namespace) -> int:
    from .conversation import inbox, questions

    store = _store(args.video_id)

    def answered() -> list[dict[str, Any]]:
        items = questions.load(store)
        if args.pergunta is not None:
            items = [q for q in items if int(q["id"]) == args.pergunta]
        return (
            [q for q in items if q.get("estado") == "respondida"]
            if args.todas or args.pergunta
            else questions.answered_unseen(store)
        )

    if args.esperar:

        def check(_: ArtifactStore) -> dict[str, list[dict[str, Any]]]:
            return {"respostas": answered()}

        box = inbox.wait(store, timeout_s=args.timeout, check=check)
        found = box["respostas"]
    else:
        found = answered()
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    elif not found:
        print("nenhuma resposta nova")
    for entry in found if not args.json else []:
        _print_answer(entry)
    if found:
        questions.mark_seen(store, [int(q["id"]) for q in found])
        return 0
    return EXIT_TIMEOUT if args.esperar else 0


def cmd_aguardar(args: argparse.Namespace) -> int:
    from .conversation import inbox

    store = _store(args.video_id)
    box = inbox.wait(store, timeout_s=args.timeout)
    if inbox.is_empty(box):
        print("nada novo (o tempo acabou): rode de novo para continuar de vigia")
        return EXIT_TIMEOUT
    if args.json:
        print(json.dumps(box, ensure_ascii=False, indent=2))
    else:
        for entry in box["respostas"]:
            print("resposta:")
            _print_answer(entry)
        if box["pedidos_imagens"]:
            keys = ", ".join(r["alvo"] for r in box["pedidos_imagens"])
            print(f"pedidos de refacao com motivo: {keys} (rode `imagens pedidos {args.video_id}`)")
        if box["comentarios_corte"]:
            print(
                f"{len(box['comentarios_corte'])} comentario(s) do corte final "
                f"(rode `corte comentarios {args.video_id}`)"
            )
    inbox.mark_seen(store, box)
    return 0


def cmd_nota(args: argparse.Namespace) -> int:
    _store(args.video_id)
    _announcer().announce(args.video_id, "nota", " ".join(args.texto.split()), step=args.etapa)
    print("nota registrada")
    return 0


def cmd_corte_comentarios(args: argparse.Namespace) -> int:
    from .review import final_cut

    store = _store(args.video_id)
    comments = final_cut.load(store) if args.todos else final_cut.pending(store)
    out = [
        {
            **c,
            "imagem_absoluta": str((store.root / c["imagem"]).resolve())
            if c.get("imagem")
            else None,
        }
        for c in comments
    ]
    final_cut.mark_seen(store)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    if not out:
        print("nenhum comentario esperando a sessao")
    for c in out:
        minutes, seconds = divmod(int(c.get("tempo_s") or 0), 60)
        clip = f" corte {c['corte']} do TikTok," if c.get("corte") else ""
        where = f"{c.get('idioma')}{clip} {minutes}:{seconds:02d}"
        print(f"#{c['id']} [{where}] {c.get('chave')} ({c.get('estado')})")
        print(f"  {c.get('texto')}")
        if c.get("link"):
            print(f"  link: {c['link']}")
        print(f"  narracao: {(c.get('narracao') or '')[:160]}")
        print(f"  imagem: {c.get('imagem_absoluta')}")
    return 0


def cmd_corte_resolver(args: argparse.Namespace) -> int:
    from .review import final_cut

    entry = final_cut.resolve(
        _store(args.video_id), args.comentario, args.resposta, discard=args.descartar
    )
    print(f"comentario #{entry['id']} {entry['estado']}")
    return 0


# -- cortes do TikTok (ADR 0010) ---------------------------------------------


def cmd_cortes_listar(args: argparse.Namespace) -> int:
    """A escolha atual e, com --candidatos, todos os trechos que cabem."""
    from .clips import Selection

    store = _store(args.video_id)
    path = store.path("cortes", "selecao.json")
    if not path.exists():
        print("os cortes ainda nao foram escolhidos (etapa cortes)")
        return 1
    selection = Selection.from_dict(store.read_json("cortes", "selecao.json"))
    if args.json:
        payload: dict[str, Any] = selection.to_dict()
        if args.candidatos:
            payload["candidatos"] = store.read_json("cortes", "candidatos.json")["candidatos"]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    for clip in selection.clips:
        c = clip.candidate
        print(f"corte {clip.number} ({', '.join(clip.langs)}): {c.id}, bloco {c.block} ({c.title})")
        for lang in clip.langs:
            span = c.span(lang)
            print(
                f"  {lang}: {span.start:.1f}-{span.end:.1f} s ({span.duration:.0f} s), "
                f"{span.first}..{span.last}"
            )
            print(f"    gancho: {clip.hook[lang]}")
            print(f"    legenda: {clip.caption[lang]!r}")
            print(f"    hashtags: {' '.join(clip.hashtags[lang])}")
    for warning in selection.warnings:
        print(f"aviso: {warning}")
    if args.candidatos:
        print("\ncandidatos:")
        for raw in store.read_json("cortes", "candidatos.json")["candidatos"]:
            pt, en = raw["pt-br"], raw["en"]
            print(
                f"  {raw['id']}: bloco {raw['bloco']} ({raw['titulo']}), "
                f"PT {pt['duracao_s']:.0f} s {pt['primeira_frase']}..{pt['ultima_frase']}, "
                f"EN {en['duracao_s']:.0f} s"
            )
    return 0


def cmd_cortes_editar(args: argparse.Namespace) -> int:
    """Muda um corte sem chamar o LLM: trecho, gancho ou legenda.

    Apaga so os renders daquele corte e devolve a etapa a fila: o worker
    renderiza o que falta e o corte final volta a esperar o revisor.
    """
    from dataclasses import replace

    from .cli import _runner
    from .clips import Candidate, Selection
    from .clips.candidates import LANGS

    store = _store(args.video_id)
    selection = Selection.from_dict(store.read_json("cortes", "selecao.json"))
    clip = selection.clip(args.corte)
    changed: list[str] = []

    if args.candidato:
        found = {
            raw["id"]: Candidate.from_dict(raw)
            for raw in store.read_json("cortes", "candidatos.json")["candidatos"]
        }
        if args.candidato not in found:
            raise ValueError(
                f"candidato {args.candidato} nao existe (veja `cortes listar --candidatos`)"
            )
        new = found[args.candidato]
        others = [c.candidate for c in selection.clips if c.number != clip.number]
        #  So os idiomas postados contam: com a conta EN parada, o trecho EN
        #  equivalente nao vai ao ar.
        posted = tuple(lang for lang in LANGS if any(lang in c.langs for c in selection.clips))
        if any(new.overlaps(other, posted) for other in others):
            raise ValueError(f"{args.candidato} se sobrepoe a outro corte")
        clip = replace(clip, candidate=new)
        changed.append(f"trecho {new.id}")
    for lang, hook, caption in (
        ("pt-br", args.gancho_pt, args.legenda_pt),
        ("en", args.gancho_en, args.legenda_en),
    ):
        if (hook or caption) and lang not in clip.langs:
            raise ValueError(f"o corte {clip.number} so e postado em {', '.join(clip.langs)}")
        if hook:
            clip = replace(clip, hook={**clip.hook, lang: " ".join(hook.split())})
            changed.append(f"gancho {lang}")
        if caption:
            clip = replace(clip, caption={**clip.caption, lang: caption.strip()})
            changed.append(f"legenda {lang}")
    if not changed:
        print("nada para mudar: use --candidato, --gancho-pt/en ou --legenda-pt/en")
        return 1

    selection.clips = [clip if c.number == clip.number else c for c in selection.clips]
    #  A ordem dos cortes segue o video: um trecho trocado pode mudar a posicao.
    selection.clips.sort(key=lambda c: c.candidate.span("pt-br").start)
    selection.clips = [replace(c, number=n) for n, c in enumerate(selection.clips, start=1)]
    store.write_json("cortes", "selecao.json", selection.to_dict(), step="cortes")

    #  Trecho trocado pode mudar a numeracao: saem os renders de todos os
    #  cortes. Gancho ou legenda: so os deste.
    numbers = [c.number for c in selection.clips] if args.candidato else [args.corte]
    for n in numbers:
        for lang in ("pt-br", "en"):
            for name in (
                f"corte-{n}.{lang}.mp4",
                f"props.{lang}.{n}.json",
                f"narracao.{lang}.{n}.wav",
            ):
                store.delete(store.path("cortes", name))
    reset = _runner().queue.reset_step(args.video_id, StepName.CORTES)
    print(f"corte {args.corte}: {', '.join(changed)}")
    print(f"de volta a fila: {', '.join(n.value for n in reset)}")
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

    q = imagens.add_parser(
        "folhas", help="folhas de miniaturas para a pre-checagem da sessao (nao e a revisao)"
    )
    q.add_argument("video_id")
    q.add_argument("--capitulo", type=int, help="so um capitulo (1, 2...; 0: thumbnail e poses)")
    q.add_argument("--por-folha", type=int, default=12, help="miniaturas por folha")
    q.set_defaults(func=cmd_imagens_folhas)

    p = sub.add_parser("perguntar", help="faz uma pergunta ao revisor na pagina (com aviso)")
    p.add_argument("video_id")
    p.add_argument("texto")
    p.add_argument("--opcao", action="append", default=[], help="uma opcao de resposta (repita)")
    p.add_argument("--etapa", help="etapa a que a pergunta se refere")
    p.add_argument("--alvo", help="imagem a que a pergunta se refere (cena-045)")
    p.add_argument("--sem-texto-livre", action="store_true", help="so as opcoes")
    p.set_defaults(func=cmd_perguntar)

    p = sub.add_parser("respostas", help="respostas do revisor as perguntas")
    p.add_argument("video_id")
    p.add_argument("--pergunta", type=int)
    p.add_argument("--todas", action="store_true", help="inclusive as ja vistas")
    p.add_argument("--esperar", action="store_true", help="espera a resposta chegar")
    p.add_argument("--timeout", type=float, default=6000.0, help="segundos (padrao: 100 min)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_respostas)

    p = sub.add_parser(
        "aguardar", help="vigia da sessao: espera resposta, pedido com motivo ou comentario"
    )
    p.add_argument("video_id")
    p.add_argument("--timeout", type=float, default=6000.0, help="segundos (padrao: 100 min)")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_aguardar)

    p = sub.add_parser("nota", help="registra uma nota da sessao na etapa (aparece na pagina)")
    p.add_argument("video_id")
    p.add_argument("texto")
    p.add_argument("--etapa", default=StepName.PESQUISA.value)
    p.set_defaults(func=cmd_nota)

    p = sub.add_parser("corte", help="comentarios do corte final (sessao)")
    corte = p.add_subparsers(dest="acao", required=True)
    q = corte.add_parser("comentarios", help="comentarios enviados pelo revisor")
    q.add_argument("video_id")
    q.add_argument("--json", action="store_true")
    q.add_argument("--todos", action="store_true")
    q.set_defaults(func=cmd_corte_comentarios)
    q = corte.add_parser("resolver", help="responde um comentario (o que foi feito)")
    q.add_argument("video_id")
    q.add_argument("comentario", type=int)
    q.add_argument("resposta")
    q.add_argument("--descartar", action="store_true", help="nao vai mudar: explica o porque")
    q.set_defaults(func=cmd_corte_resolver)

    p = sub.add_parser("cortes", help="cortes do TikTok: ver e mudar sem chamar o LLM (sessao)")
    cortes = p.add_subparsers(dest="acao", required=True)
    q = cortes.add_parser("listar", help="os cortes escolhidos, com trecho, gancho e legenda")
    q.add_argument("video_id")
    q.add_argument("--candidatos", action="store_true", help="tambem os trechos que cabem")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_cortes_listar)
    q = cortes.add_parser(
        "editar", help="troca trecho, gancho ou legenda de um corte e re-renderiza"
    )
    q.add_argument("video_id")
    q.add_argument("corte", type=int, help="numero do corte (1, 2, ...), como em `listar`")
    q.add_argument("--candidato", help="outro trecho, por id (c07); veja `listar --candidatos`")
    q.add_argument("--gancho-pt")
    q.add_argument("--gancho-en")
    q.add_argument("--legenda-pt")
    q.add_argument("--legenda-en")
    q.set_defaults(func=cmd_cortes_editar)
