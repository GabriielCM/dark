"""Linha de comando.

`mundoantigo <comando>`. Os comandos cobrem a operacao inteira sem o painel,
o que e util para diagnostico e para rodar o worker em segundo plano.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

from .config import get_settings, load_settings
from .costs import CostRecorder, PriceTable
from .db.session import get_sessionmaker, init_db
from .paths import get_paths
from .pipeline import Runner, StepName, Worker, video_progress
from .providers import ProviderRegistry, fake_registry


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    #  httpx loga cada request em INFO; ruido demais para o dia a dia.
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _runner(*, ensaio: bool = False) -> Runner:
    settings = get_settings()
    sessions = get_sessionmaker()
    costs = CostRecorder(settings.budget, PriceTable.from_yaml(), sessions)
    providers = (
        fake_registry(settings, costs)
        if ensaio
        else ProviderRegistry(settings=settings, costs=costs)
    )
    return Runner.build(settings=settings, providers=providers, session_factory=sessions)


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    paths = get_paths()
    paths.ensure()
    init_db()
    settings = load_settings()
    print(f"banco:      {paths.db_file}")
    print(f"videos:     {paths.videos}")
    print(f"livros:     {paths.books}")
    print(f"biblioteca: {paths.library}")
    print(f"canais:     {', '.join(sorted(settings.channels))}")
    print(f"estilo:     {settings.style.id} ({settings.style.status})")
    print(f"teto:       US$ {settings.budget.hard_limit_usd:.2f}/mes")
    if not (paths.root / ".env").exists():
        print("\naviso: .env ausente. Copie .env.example e preencha as chaves.")
    return 0


def cmd_nova(args: argparse.Namespace) -> int:
    runner = _runner()
    video_id = runner.queue.enqueue_video(args.tema, pillar=args.pilar, priority=args.prioridade)
    print(video_id)
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    runner = _runner(ensaio=args.ensaio)
    worker = Worker(runner, poll_seconds=args.intervalo)
    if args.ensaio:
        print("modo ensaio: provedores falsos, nenhuma chamada externa\n")

    async def main() -> int:
        if args.uma_vez:
            executed = await worker.drain(limit=args.limite)
            print(f"{executed} etapa(s) executada(s)")
        else:
            print("worker rodando. ctrl+c para parar.")
            try:
                await worker.run_forever()
            except (KeyboardInterrupt, asyncio.CancelledError):
                print("\nencerrando")
        return 0

    return asyncio.run(main())


def cmd_status(args: argparse.Namespace) -> int:
    sessions = get_sessionmaker()
    settings = get_settings()
    costs = CostRecorder(settings.budget, PriceTable.from_yaml(), sessions)

    if args.video_id:
        progress = video_progress(sessions, args.video_id)
        if not progress:
            print(f"producao {args.video_id} nao existe", file=sys.stderr)
            return 1
        if args.json:
            print(json.dumps(progress, ensure_ascii=False, indent=2, default=str))
            return 0
        marks = {
            "done": "OK",
            "skipped": "--",
            "running": "~~",
            "blocked": ">>",
            "failed": "XX",
            "pending": "..",
        }
        print(f"{progress['tema']}  [{progress['estado']}, {progress['progresso']}%]")
        print(f"custo: US$ {costs.spent_on_video(args.video_id):.4f}\n")
        for step in progress["etapas"]:
            mark = marks.get(step["estado"], "??")
            detail = step["resumo"] or step["erro"] or ""
            print(f"  {mark} {step['nome']:<14} {detail[:88]}")
        if progress["bloqueio"]:
            print(f"\nbloqueio: {progress['bloqueio']}")
        return 0

    from sqlalchemy import select

    from .db.models import Video

    with sessions() as s:
        videos = list(s.execute(select(Video).order_by(Video.created_at.desc())).scalars().all())
    status = costs.status()
    print(
        f"orcamento {status.month}: US$ {status.spent_usd:.4f} de US$ {status.hard_limit_usd:.2f}"
    )
    if status.over_hard:
        print("  TETO ATINGIDO: chamadas pagas bloqueadas")
    elif status.over_soft:
        print("  acima do aviso")
    print()
    if not videos:
        print("nenhuma producao na fila")
        return 0
    for video in videos:
        print(f"  {video.state.value:<14} {video.id}  {video.topic[:52]}")
    return 0


def cmd_custos(args: argparse.Namespace) -> int:
    settings = get_settings()
    costs = CostRecorder(settings.budget, PriceTable.from_yaml(), get_sessionmaker())
    status = costs.status()
    print(
        f"mes {status.month}: US$ {status.spent_usd:.4f} de US$ {status.hard_limit_usd:.2f} "
        f"({status.percent:.0f}%)\n"
    )
    rows = costs.breakdown_by_step(month=args.mes)
    if rows:
        print("por etapa:")
        for step, amount, count in rows:
            print(f"  {step:<16} US$ {amount:>9.4f}  ({count} chamadas)")
    videos = costs.breakdown_by_video(month=args.mes)
    if videos:
        print("\npor producao:")
        for video_id, amount in videos:
            print(f"  {video_id:<40} US$ {amount:>9.4f}")
    return 0


def cmd_aprovar(args: argparse.Namespace) -> int:
    _runner().approve(args.video_id, reviewer=args.revisor)
    print(f"{args.video_id} aprovado")
    return 0


def cmd_rejeitar(args: argparse.Namespace) -> int:
    _runner().reject(args.video_id, args.motivo, redo_from=StepName(args.refazer_de))
    print(f"{args.video_id} rejeitado; refazendo a partir de {args.refazer_de}")
    return 0


def cmd_refazer(args: argparse.Namespace) -> int:
    runner = _runner()
    if args.apagar:
        from .artifacts import ArtifactStore

        stages = {
            "pesquisa": "pesquisa",
            "roteiro": "roteiro",
            "adaptacao_en": "adaptacao",
            "cenas": "cenas",
            "assets": "assets",
            "narracao": "narracao",
            "montagem": "montagem",
            "metadados": "metadados",
        }
        stage = stages.get(args.etapa)
        if stage:
            ArtifactStore(args.video_id).clear_stage(stage)
            print(f"artefatos de `{stage}` apagados")
    runner.queue.reset_step(args.video_id, StepName(args.etapa))
    print(f"{args.video_id} reenfileirado a partir de {args.etapa}")
    return 0


def cmd_livro(args: argparse.Namespace) -> int:
    from .books import BookIngestor

    settings = get_settings()
    sessions = get_sessionmaker()
    costs = CostRecorder(settings.budget, PriceTable.from_yaml(), sessions)
    providers = ProviderRegistry(settings=settings, costs=costs)
    ingestor = BookIngestor(sessions)

    path = Path(args.arquivo).expanduser().resolve()
    if not path.exists():
        print(f"arquivo nao encontrado: {path}", file=sys.stderr)
        return 1

    print(f"extraindo {path.name}...")
    extracted = ingestor.extract(path)
    print(f"  {extracted.page_count} paginas/secoes, OCR: {'sim' if extracted.ocr_used else 'nao'}")

    print("identificando metadados...")
    metadata = asyncio.run(ingestor.identify(extracted, path.name, providers))

    from .books.ingest import sha256_of

    stored = ingestor.store_file(path, sha256_of(path)[:12])
    book = ingestor.register(stored, extracted, metadata)

    print(f"\nlivro {book.id}: {book.title or path.name}")
    print(
        f"autor: {book.author or '?'}" + (f" · trad. {book.translator}" if book.translator else "")
    )
    print(f"direitos: {book.rights_status.value}")
    print(f"  {book.rights_reason}")
    return 0


def cmd_painel(args: argparse.Namespace) -> int:
    from .web import run

    run()
    return 0


def cmd_contrato(args: argparse.Namespace) -> int:
    """Grava o snapshot do contrato de props para o lado TS comparar."""
    from .render.remotion import write_contract_snapshot

    destination = Path(args.saida) if args.saida else get_paths().data / "contrato.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_contract_snapshot(destination)
    print(destination)
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mundoantigo",
        description="Pipeline de videos narrados de historia antiga (PT-BR e EN).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log detalhado")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("init", help="cria diretorios e banco, valida a configuracao")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("nova", help="enfileira uma producao")
    p.add_argument("tema")
    p.add_argument("--pilar", default="engenharia")
    p.add_argument("--prioridade", type=int, default=0)
    p.set_defaults(func=cmd_nova)

    p = sub.add_parser("worker", help="executa as etapas da fila")
    p.add_argument("--uma-vez", action="store_true", help="drena a fila e sai")
    p.add_argument("--limite", type=int, default=100)
    p.add_argument("--intervalo", type=float, default=5.0)
    p.add_argument(
        "--ensaio", action="store_true", help="provedores falsos: percorre o pipeline sem gastar"
    )
    p.set_defaults(func=cmd_worker)

    p = sub.add_parser("status", help="estado da fila ou de uma producao")
    p.add_argument("video_id", nargs="?")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("custos", help="gasto do mes por etapa e producao")
    p.add_argument("--mes", help="AAAA-MM (padrao: mes corrente)")
    p.set_defaults(func=cmd_custos)

    p = sub.add_parser("aprovar", help="aprova o corte final")
    p.add_argument("video_id")
    p.add_argument("--revisor", default="cli")
    p.set_defaults(func=cmd_aprovar)

    p = sub.add_parser("rejeitar", help="rejeita informando o motivo")
    p.add_argument("video_id")
    p.add_argument("motivo")
    p.add_argument("--refazer-de", default=StepName.ROTEIRO.value)
    p.set_defaults(func=cmd_rejeitar)

    p = sub.add_parser("refazer", help="reenfileira a partir de uma etapa")
    p.add_argument("video_id")
    p.add_argument("etapa")
    p.add_argument(
        "--apagar", action="store_true", help="apaga os artefatos: forca refazer trabalho ja pago"
    )
    p.set_defaults(func=cmd_refazer)

    p = sub.add_parser("livro", help="ingere um PDF ou ePub")
    p.add_argument("arquivo")
    p.set_defaults(func=cmd_livro)

    p = sub.add_parser("painel", help="sobe o painel web local")
    p.set_defaults(func=cmd_painel)

    p = sub.add_parser("contrato", help="grava o snapshot do contrato de props")
    p.add_argument("--saida")
    p.set_defaults(func=cmd_contrato)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.getLogger("mundoantigo").debug("falha", exc_info=True)
        print(f"erro: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
