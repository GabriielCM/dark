"""Validacao e importacao do que a sessao produziu.

A sessao grava tres arquivos numa pasta (dossie.json, roteiro.pt-br.json e
relatorio_fatos.json). Aqui eles sao validados contra o esquema e entre si, e
so entao copiados para as pastas das etapas 2 e 3, com sidecar de provedor
`claude-code`. A partir dai a fila trata as duas etapas como concluidas e o
gate de fatos avalia o relatorio como sempre (nenhuma renderizacao sem gate).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ValidationError

from ..artifacts import ArtifactStore
from ..config import ChannelConfig, FactsConfig
from ..pipeline.fact_gate import FactGate
from ..text.titles import SCREEN_TITLE_MAX_CHARS, screen_title
from .schemas import Dossie, RelatorioFatos, Roteiro

FILES = {
    "dossie": "dossie.json",
    "roteiro": "roteiro.pt-br.json",
    "relatorio": "relatorio_fatos.json",
}
PROMPT_REF = "sessao/roteiro@v1"
#  Folga sobre a meta de duracao do canal (palavras = minutos x ppm).
WORD_TOLERANCE = 0.10
_ACCENTED = re.compile(r"[áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ]")
#  Anotacoes da sessao que vazavam para o titulo da fonte ("trad.", "sobre").
_PT_SOURCE_WORDS = re.compile(r"\b(?:trad|sobre)\b", re.IGNORECASE)


def _portuguese_url(url: str | None) -> bool:
    """Fonte publicada em portugues: dominio .br/.pt, pt.wikipedia, /pt/ no caminho."""
    if not url:
        return False
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.endswith((".br", ".pt")) or host.startswith("pt."):
        return True
    segments = {s.lower() for s in parts.path.split("/")}
    return bool(segments & {"pt", "pt-br", "portuguese"})


def _looks_portuguese(title: str) -> bool:
    return bool(_ACCENTED.search(title) or _PT_SOURCE_WORDS.search(title))


@dataclass
class ImportReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    words: int = 0
    minutes: float = 0.0
    gate: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def _load(folder: Path, key: str, model: type[BaseModel], report: ImportReport) -> Any:
    path = folder / FILES[key]
    if not path.exists():
        report.errors.append(f"{FILES[key]} ausente em {folder}")
        return None
    try:
        return model.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        report.errors.append(f"{FILES[key]}: JSON invalido ({exc})")
    except ValidationError as exc:
        for error in exc.errors()[:10]:
            where = ".".join(str(p) for p in error["loc"])
            report.errors.append(f"{FILES[key]}: {where}: {error['msg']}")
    return None


def count_words(roteiro: Roteiro) -> int:
    return sum(len(block.narracao.split()) for block in roteiro.blocos)


def validate(
    dossie: Dossie,
    roteiro: Roteiro,
    relatorio: RelatorioFatos,
    *,
    channel: ChannelConfig,
    facts: FactsConfig,
    report: ImportReport | None = None,
    sample: bool = False,
) -> ImportReport:
    """Confere a sessao contra o esquema e entre si.

    `sample` e a amostra curta (~60 s) usada para comparar a saida com os
    videos entregues: dispensa a meta de duracao do canal e os 3 capitulos,
    que viram avisos. O resto, gate de fatos inclusive, vale igual.
    """
    report = report or ImportReport()
    source_ids = {f.id for f in dossie.fontes}
    source_urls = {f.url for f in dossie.fontes if f.url}
    claim_ids = {a.id for block in dossie.blocos for a in block.afirmacoes}

    for claim in (a for block in dossie.blocos for a in block.afirmacoes):
        missing = [s for s in claim.fontes if s not in source_ids]
        if missing:
            report.errors.append(f"dossie: afirmacao {claim.id} cita fontes inexistentes {missing}")
    for source in dossie.fontes:
        if source.titulo and _looks_portuguese(source.titulo) and not _portuguese_url(source.url):
            #  O mesmo titulo vai para a descricao EN ("Wikipédia", "Universidade
            #  de Amsterdã" no pacote EN do Gize).
            report.warnings.append(
                f"fonte {source.id}: titulo em portugues ({source.titulo!r}) numa fonte em "
                "outro idioma. Ele vai igual para a descricao EN: use o titulo como publicado."
            )

    if len(roteiro.blocos) < 3:
        message = "roteiro com menos de 3 blocos: o YouTube exige 3 capitulos"
        (report.warnings if sample else report.errors).append(message)
    for index, block in enumerate(roteiro.blocos):
        short = screen_title(block.titulo)
        if len(short) > SCREEN_TITLE_MAX_CHARS:
            report.warnings.append(
                f"bloco {index}: o titulo na tela ({short!r}) tem {len(short)} caracteres; "
                f"acima de {SCREEN_TITLE_MAX_CHARS} ele encolhe. Use 'Curto: complemento'."
            )
        unknown = [c for c in block.afirmacoes_usadas if c not in claim_ids]
        if unknown:
            report.errors.append(f"roteiro: bloco {index} usa afirmacoes fora do dossie {unknown}")
        for comment in block.comentarios_mc:
            if not 2 <= len(comment.split()) <= 10:
                report.warnings.append(
                    f"bloco {index}: balao com {len(comment.split())} palavras: {comment!r}"
                )
    if roteiro.pedidos_de_pesquisa:
        report.errors.append(
            f"o roteiro ainda pede pesquisa: {roteiro.pedidos_de_pesquisa}. "
            "Resolva antes de importar."
        )

    for item in relatorio.itens:
        if not 0 <= item.bloco < len(roteiro.blocos):
            report.errors.append(f"relatorio: item {item.id} aponta para o bloco {item.bloco}")
        stray = [s for s in item.fontes if s not in source_ids and s not in source_urls]
        if stray:
            report.errors.append(f"relatorio: item {item.id} cita fontes fora do dossie {stray}")

    narration = " ".join(block.narracao for block in roteiro.blocos)
    if not _ACCENTED.search(narration):
        report.errors.append("narracao sem nenhum acento: o texto em PT precisa de acentuacao")

    report.words = count_words(roteiro)
    report.minutes = round(report.words / max(channel.wpm, 1), 1)
    low = channel.target_min_minutes * channel.wpm * (1 - WORD_TOLERANCE)
    high = channel.target_max_minutes * channel.wpm * (1 + WORD_TOLERANCE)
    if not low <= report.words <= high:
        message = (
            f"{report.words} palavras (~{report.minutes} min) fora da meta de "
            f"{channel.target_min_minutes} a {channel.target_max_minutes} min "
            f"({int(low)} a {int(high)} palavras)"
        )
        (report.warnings if sample else report.errors).append(message)

    balloons = sum(len(block.comentarios_mc) for block in roteiro.blocos)
    if balloons < report.minutes:
        report.warnings.append(
            f"{balloons} balao(oes) para ~{report.minutes} min: os videos antigos tinham "
            "cerca de um a cada 30 a 45 s"
        )
    if not roteiro.figurino:
        report.warnings.append("sem `figurino`: o MC usara o figurino padrao do guia de estilo")
    if not roteiro.ambientacao:
        report.warnings.append(
            "sem `ambientacao`: as imagens nao recebem epoca e lugar, e pessoas e "
            "cidades genericas tendem a sair modernas"
        )

    gate = FactGate(facts)
    items = gate.downgrade_unsourced(gate.parse(relatorio.model_dump()))
    verdict = gate.evaluate(items)
    report.gate = {"aprovado": verdict.passed, "motivo": verdict.reason, "contagem": verdict.counts}
    if not verdict.passed:
        report.warnings.append(
            f"o gate de fatos vai bloquear: {verdict.reason}. Corrija na sessao e reimporte."
        )
    return report


def import_session(
    folder: Path,
    store: ArtifactStore,
    *,
    channel: ChannelConfig,
    facts: FactsConfig,
    validate_only: bool = False,
    sample: bool = False,
) -> ImportReport:
    report = ImportReport()
    dossie = _load(folder, "dossie", Dossie, report)
    roteiro = _load(folder, "roteiro", Roteiro, report)
    relatorio = _load(folder, "relatorio", RelatorioFatos, report)
    if dossie is None or roteiro is None or relatorio is None:
        return report
    validate(dossie, roteiro, relatorio, channel=channel, facts=facts, report=report, sample=sample)
    if not report.ok or validate_only:
        return report

    meta: dict[str, Any] = {"provider": "claude-code", "model": "sessao", "prompt_ref": PROMPT_REF}
    store.write_json(
        "pesquisa", "dossie.json", dossie.model_dump(exclude_none=True), step="pesquisa", **meta
    )
    script = roteiro.model_dump(exclude_none=True)
    script["palavras_total"] = report.words
    store.write_json("roteiro", "roteiro.pt-br.json", script, step="roteiro", **meta)
    store.write_json(
        "roteiro", "relatorio_fatos.json", relatorio.model_dump(), step="roteiro", **meta
    )
    return report
