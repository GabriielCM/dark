"""Linha de comando.

`mundoantigo <comando>`. Os comandos cobrem a operacao inteira sem o painel,
o que e util para diagnostico e para rodar o worker em segundo plano.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import logging
import sys
from pathlib import Path

from .artifacts import ArtifactStore
from .config import get_settings, load_settings
from .costs import CostRecorder, PriceTable
from .db.session import get_sessionmaker, init_db
from .paths import get_paths
from .pipeline import Runner, StepName, Worker, video_progress
from .providers import ProviderRegistry, fake_registry
from .providers.image import ImageProvider
from .session.importer import ImportReport


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
    if ensaio:
        #  O ensaio valida o caminho inteiro, nao a imagem: render pequeno e
        #  rapido em vez de 12 minutos em 1080p por idioma.
        #  E o LLM falso faz o papel da sessao: o ensaio percorre tudo sozinho.
        settings = dataclasses.replace(
            settings,
            render=dataclasses.replace(settings.render, width=640, height=360, fps=15),
            app={
                **settings.app,
                "roteiro": {"modo": "api"},
                "referencias": {**settings.app.get("referencias", {}), "ranking": "titulo"},
            },
        )
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


def _print_import(report: ImportReport) -> None:
    print(f"{report.words} palavras (~{report.minutes} min)")
    if report.gate:
        status = "aprova" if report.gate["aprovado"] else "BLOQUEIA"
        print(f"gate de fatos: {status} ({report.gate['motivo']})")
    for warning in report.warnings:
        print(f"  aviso: {warning}")
    for error in report.errors:
        print(f"  ERRO: {error}", file=sys.stderr)


def cmd_nova(args: argparse.Namespace) -> int:
    from .session.importer import import_session

    runner = _runner()
    settings = get_settings()
    folder = Path(args.roteiro_da_sessao).resolve() if args.roteiro_da_sessao else None
    if folder is not None:
        #  Valida antes de criar a producao: roteiro com erro nao vira fila.
        check = import_session(
            folder,
            ArtifactStore("_validacao"),
            channel=settings.channel("pt-br"),
            facts=settings.facts,
            validate_only=True,
        )
        _print_import(check)
        if not check.ok:
            return 1
    video_id = runner.queue.enqueue_video(args.tema, pillar=args.pilar, priority=args.prioridade)
    if folder is not None:
        import_session(
            folder,
            ArtifactStore(video_id),
            channel=settings.channel("pt-br"),
            facts=settings.facts,
        )
    print(video_id)
    return 0


def cmd_importar_roteiro(args: argparse.Namespace) -> int:
    from .session.importer import import_session

    settings = get_settings()
    folder = Path(args.pasta).resolve()
    store = ArtifactStore(args.video_id)
    report = import_session(
        folder,
        store,
        channel=settings.channel("pt-br"),
        facts=settings.facts,
        validate_only=True,
    )
    _print_import(report)
    if not report.ok or args.validar_apenas:
        return 0 if report.ok else 1
    runner = _runner()
    #  Um roteiro novo invalida tudo que veio do anterior: apaga as saidas da
    #  pesquisa em diante e so entao grava os arquivos da sessao.
    runner.redo(args.video_id, [StepName.PESQUISA], reason=args.motivo)
    import_session(folder, store, channel=settings.channel("pt-br"), facts=settings.facts)
    print(f"{args.video_id}: roteiro da sessao importado; a fila segue sozinha")
    return 0


def cmd_worker(args: argparse.Namespace) -> int:
    runner = _runner(ensaio=args.ensaio)
    runner.queue.sync_pipeline()
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
    _runner().approve(args.video_id, gate=StepName(args.etapa), reviewer=args.revisor)
    print(f"{args.video_id}: {args.etapa} aprovada")
    return 0


def cmd_rejeitar(args: argparse.Namespace) -> int:
    _runner().reject(args.video_id, args.motivo, redo_from=StepName(args.refazer_de))
    print(f"{args.video_id} rejeitado; refazendo a partir de {args.refazer_de}")
    return 0


def cmd_refazer(args: argparse.Namespace) -> int:
    runner = _runner()
    step = StepName(args.etapa)
    if args.apagar:
        #  Apaga as saidas da etapa e de tudo que depende dela: o trabalho
        #  ja pago e refeito de verdade, nao so pulado de novo.
        reset = runner.redo(args.video_id, [step])
    else:
        reset = runner.queue.reset_step(args.video_id, step)
    print(f"{args.video_id}: de volta a fila -> {', '.join(n.value for n in reset)}")
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


def cmd_backup(args: argparse.Namespace) -> int:
    from .ops import run_backup

    settings = get_settings()
    destination = args.destino or settings.backup.destination
    if not destination:
        print("backup desligado: defina backup.destino ou MA_BACKUP_DESTINO", file=sys.stderr)
        return 1
    paths = get_paths()
    report = run_backup(
        root=paths.root,
        db_file=paths.db_file,
        folders={
            "videos": paths.videos,
            "biblioteca": paths.library,
            "livros": paths.books,
            "data": paths.data,
        },
        extras=[Path(p) for p in settings.backup.extras],
        destination=Path(destination),
    )
    for item in report.items:
        mark = "OK" if item.ok else "XX"
        detail = f"  ({item.detail})" if item.detail else ""
        print(f"  {mark} {item.name:<22} {item.files:>7} arq  {item.bytes / 1e9:>8.2f} GB{detail}")
    print(f"\n{'concluido' if report.ok else 'COM FALHAS'}: {report.destination}")
    return 0 if report.ok else 1


def _image_provider() -> ImageProvider:
    settings = get_settings()
    costs = CostRecorder(settings.budget, PriceTable.from_yaml(), get_sessionmaker())
    init_db()
    return ProviderRegistry(settings=settings, costs=costs).image()


def cmd_estilo_calibrar(args: argparse.Namespace) -> int:
    from .style.calibration import Calibration, run_calibration

    paths = get_paths()
    calibration = Calibration.from_yaml(paths.config / "estilo" / "calibracao.yaml", paths.root)
    seed = args.semente if args.semente is not None else calibration.seed
    out_dir = paths.data / "calibracao" / f"semente-{seed}"
    sheet = asyncio.run(
        run_calibration(
            calibration,
            _image_provider(),
            out_dir,
            variants=args.variantes.split(",") if args.variantes else None,
            scene_ids=args.cenas.split(",") if args.cenas else None,
            seed=seed,
        )
    )
    print(sheet)
    return 0


def cmd_personagem_poses(args: argparse.Namespace) -> int:
    from .pipeline.queue import slugify
    from .style.calibration import Calibration
    from .style.character import generate_pose_set

    paths = get_paths()
    calibration = Calibration.from_yaml(paths.config / "estilo" / "calibracao.yaml", paths.root)
    style = (
        calibration.variants[args.variante] if args.variante else get_settings().style.base_prompt
    )
    out_dir = Path(args.saida) if args.saida else paths.character_library / slugify(args.figurino)
    sprites = asyncio.run(
        generate_pose_set(
            _image_provider(),
            out_dir,
            style=style,
            character=calibration.character,
            costume=args.figurino,
            restrictions=calibration.restrictions,
            seed=args.semente,
            poses=args.poses.split(",") if args.poses else None,
            method=args.recorte,
        )
    )
    for sprite in sprites:
        print(f"  {sprite.pose:<16} {sprite.path}  cabeca={sprite.head}")
    return 0


def cmd_voz_identificar(args: argparse.Namespace) -> int:
    from .pipeline.queue import slugify
    from .providers.gpu import release_comfyui
    from .voice.identify import (
        ecapa_embedder,
        identify,
        kokoro_synthesizer,
        whisper_transcriber,
    )

    paths = get_paths()
    video = Path(args.video).expanduser().resolve()
    if not video.exists():
        print(f"video nao encontrado: {video}", file=sys.stderr)
        return 1
    out_dir = Path(args.saida) if args.saida else paths.data / "voz_id" / slugify(video.stem)
    device = args.dispositivo
    if device == "cuda":
        #  O ComfyUI guarda os modelos na VRAM entre chamadas; sem soltar,
        #  Whisper, Kokoro e ECAPA nao cabem nos 12 GB.
        comfy = get_settings().providers.get("imagem", {}).get("comfyui", {})
        asyncio.run(release_comfyui(comfy.get("url")))

    report = identify(
        video,
        out_dir,
        transcribe=whisper_transcriber(device),
        synthesizer_for=lambda _language: kokoro_synthesizer(_language, device),
        embed=ecapa_embedder(paths.data / "modelos", device),
        windows=args.janelas,
        window_s=args.duracao,
        voices=args.vozes.split(",") if args.vozes else None,
    )
    print(f"idioma: {report['idioma']}\n")
    for row in report["ranking"][:8]:
        print(f"  {row['voice']:<22} semelhanca {row['score']:.3f}  velocidade {row['speed']}")
    for row in report["misturas"]:
        print(f"  {row['voice']:<22} semelhanca {row['score']:.3f}  (mistura)")
    print(f"\namostras para ouvir: {out_dir}")
    return 0


def cmd_voz_aplicar(args: argparse.Namespace) -> int:
    from .voice.identify import apply_voice

    channel_file = get_paths().config / "canais" / f"{args.canal}.yaml"
    if not channel_file.exists():
        print(f"canal desconhecido: {args.canal}", file=sys.stderr)
        return 1
    apply_voice(channel_file, args.voz, args.velocidade)
    print(f"{args.canal}: voz {args.voz}, velocidade {args.velocidade}")
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
    p.add_argument(
        "--roteiro-da-sessao", help="pasta com dossie, roteiro e relatorio feitos na sessao"
    )
    p.set_defaults(func=cmd_nova)

    p = sub.add_parser("importar-roteiro", help="valida e importa o roteiro feito na sessao")
    p.add_argument("video_id")
    p.add_argument("pasta")
    p.add_argument("--validar-apenas", action="store_true")
    p.add_argument("--motivo", help="por que o roteiro foi refeito (vai para o historico)")
    p.set_defaults(func=cmd_importar_roteiro)

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

    p = sub.add_parser("aprovar", help="aprova um portao humano (imagens ou corte final)")
    p.add_argument("video_id")
    p.add_argument(
        "--etapa",
        default=StepName.REVISAO.value,
        choices=[StepName.REVISAO.value, StepName.REVISAO_IMAGENS.value],
    )
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

    p = sub.add_parser("estilo", help="ferramentas do estilo visual")
    estilo = p.add_subparsers(dest="acao", required=True)
    q = estilo.add_parser("calibrar", help="refaz a folha de 17/09 com as variantes de prompt")
    q.add_argument("--variantes", help="ids separados por virgula (padrao: todas)")
    q.add_argument("--cenas", help="prefixos de cena separados por virgula (ex.: 01,09)")
    q.add_argument("--semente", type=int)
    q.set_defaults(func=cmd_estilo_calibrar)

    p = sub.add_parser("personagem", help="conjunto de poses do MC")
    personagem = p.add_subparsers(dest="acao", required=True)
    q = personagem.add_parser("poses", help="gera e recorta as poses com um figurino")
    q.add_argument("--figurino", required=True, help="ex.: 'a cream tunic and a black cloak'")
    q.add_argument("--semente", type=int, default=11)
    q.add_argument("--poses", help="ids separados por virgula (padrao: todas)")
    q.add_argument("--variante", help="variante de estilo de calibracao.yaml")
    q.add_argument("--recorte", choices=["branco", "rembg"], default="branco")
    q.add_argument("--saida", help="pasta de saida (padrao: biblioteca/personagem/<figurino>)")
    q.set_defaults(func=cmd_personagem_poses)

    p = sub.add_parser("voz", help="identificacao e escolha da voz dos canais")
    voz = p.add_subparsers(dest="acao", required=True)
    q = voz.add_parser("identificar", help="descobre qual voz do Kokoro narra um video")
    q.add_argument("video")
    q.add_argument("--janelas", type=int, default=3)
    q.add_argument("--duracao", type=float, default=20.0, help="segundos por janela")
    q.add_argument("--vozes", help="restringe as candidatas (separadas por virgula)")
    q.add_argument("--dispositivo", choices=["cuda", "cpu"], default="cuda")
    q.add_argument("--saida")
    q.set_defaults(func=cmd_voz_identificar)
    q = voz.add_parser("aplicar", help="grava a voz escolhida no YAML do canal")
    q.add_argument("canal", help="pt-br ou en")
    q.add_argument("voz", help="ex.: pm_alex ou pm_alex,pm_santa")
    q.add_argument("--velocidade", type=float, default=1.0)
    q.set_defaults(func=cmd_voz_aplicar)

    p = sub.add_parser("backup", help="espelha banco, videos e bibliotecas no disco de backup")
    p.add_argument("--destino", help="sobrescreve backup.destino do app.yaml")
    p.set_defaults(func=cmd_backup)

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
