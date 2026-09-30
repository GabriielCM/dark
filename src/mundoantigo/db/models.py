"""Modelos do banco.

Uma "video" aqui e uma *producao*: um roteiro revisado que gera dois videos,
PT-BR e EN, com as mesmas imagens (brief, secao 2). O identificador e o
`video_id` que aparece em `videos/<video_id>/` e no registrador de custos.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Datetime que volta do banco com fuso, sempre UTC.

    O SQLite nao guarda fuso: um `datetime` com timezone entra e volta ingenuo.
    Comparar o valor lido com `datetime.now(UTC)` levanta TypeError — e a fila
    compara exatamente isso o tempo todo (lease vencido, espera exponencial).
    Este decorador normaliza nas duas pontas para que o problema nao exista.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            #  Valor ingenuo vindo do codigo: tratamos como UTC, que e a unica
            #  convencao do projeto.
            return value
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSON, list[Any]: JSON}


# --------------------------------------------------------------------------
# Enums
# --------------------------------------------------------------------------


class VideoState(enum.StrEnum):
    """Estado da producao. Espelha as etapas do CLAUDE.md."""

    PAUTA = "pauta"
    PESQUISA = "pesquisa"
    ROTEIRO = "roteiro"
    GATE_FATOS = "gate_fatos"
    ADAPTACAO_EN = "adaptacao_en"
    NARRACAO = "narracao"
    CENAS = "cenas"
    REFERENCIAS = "referencias"
    ASSETS = "assets"
    PRE_CHECAGEM = "pre_checagem"
    REVISAO_IMAGENS = "revisao_imagens"
    TRILHA = "trilha"
    METADADOS = "metadados"
    MONTAGEM = "montagem"
    REVISAO = "revisao"
    #  A ultima etapa monta o pacote; `ENTREGUE` so vale quando ela termina. Sem
    #  essa distincao, a producao entraria no estado terminal com a ultima
    #  etapa ainda pendente — e nunca seria executada.
    EMPACOTANDO = "empacotando"
    ENTREGUE = "entregue"
    # Estados terminais fora da linha principal:
    REJEITADO = "rejeitado"
    ARQUIVADO = "arquivado"


class StepState(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    #  Esperando humano (gate de fatos, revisao) ou teto de orcamento.
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class Confidence(enum.StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class RightsStatus(enum.StrEnum):
    """Classificacao de direitos (brief 4.2)."""

    #  Dominio publico confirmado — pode adaptar e narrar, com contexto.
    LIVRE = "livre"
    #  Protegida ou incerta — entra apenas como fonte de fatos.
    FONTE_APENAS = "fonte_apenas"
    #  Ainda nao classificada.
    NAO_CLASSIFICADA = "nao_classificada"


class TopicSource(enum.StrEnum):
    MANUAL = "manual"
    SUGERIDO = "sugerido"
    LIVRO = "livro"


# --------------------------------------------------------------------------
# Producao
# --------------------------------------------------------------------------


class Video(Base):
    """Uma producao: um roteiro que vira dois videos."""

    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    topic: Mapped[str] = mapped_column(Text)
    pillar: Mapped[str] = mapped_column(String(64), default="engenharia")
    source: Mapped[TopicSource] = mapped_column(
        Enum(TopicSource, native_enum=False), default=TopicSource.MANUAL
    )
    state: Mapped[VideoState] = mapped_column(
        Enum(VideoState, native_enum=False), default=VideoState.PAUTA, index=True
    )

    #  Origem em livro, quando houver (brief 4.1: um livro vira uma serie).
    book_id: Mapped[str | None] = mapped_column(ForeignKey("books.id"), default=None)
    book_chapter: Mapped[int | None] = mapped_column(Integer, default=None)

    #  Preenchidos ao longo do pipeline.
    title_pt: Mapped[str | None] = mapped_column(Text, default=None)
    title_en: Mapped[str | None] = mapped_column(Text, default=None)

    #  Revisao humana (unico ponto — brief 3.5).
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    review_rejection_reason: Mapped[str | None] = mapped_column(Text, default=None)

    #  Motivo de bloqueio visivel no painel (gate de fatos, orcamento).
    blocked_reason: Mapped[str | None] = mapped_column(Text, default=None)

    priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    steps: Mapped[list[StepRecord]] = relationship(
        back_populates="video", cascade="all, delete-orphan", order_by="StepRecord.ordinal"
    )
    facts: Mapped[list[FactItem]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    costs: Mapped[list[CostEntry]] = relationship(back_populates="video")
    book: Mapped[Book | None] = relationship(back_populates="videos")

    def __repr__(self) -> str:  # pragma: no cover - conveniencia
        return f"<Video {self.id} {self.state.value}>"


class StepRecord(Base):
    """Uma etapa de uma producao. A fila trabalha sobre esta tabela (ADR 0002)."""

    __tablename__ = "steps"
    __table_args__ = (
        UniqueConstraint("video_id", "name", name="uq_step_por_video"),
        Index("ix_steps_fila", "state", "run_after"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    ordinal: Mapped[int] = mapped_column(Integer)
    state: Mapped[StepState] = mapped_column(
        Enum(StepState, native_enum=False), default=StepState.PENDING, index=True
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    #  Lease: `running` vencido volta para `pending` sozinho (ADR 0002).
    lease_until: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    worker_id: Mapped[str | None] = mapped_column(String(64), default=None)
    #  Espera exponencial entre tentativas.
    run_after: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    duration_s: Mapped[float | None] = mapped_column(Float, default=None)

    error: Mapped[str | None] = mapped_column(Text, default=None)
    error_kind: Mapped[str | None] = mapped_column(String(64), default=None)
    #  Resumo do que a etapa produziu, para o painel.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    video: Mapped[Video] = relationship(back_populates="steps")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Step {self.video_id}/{self.name} {self.state.value}>"


class FactItem(Base):
    """Uma linha do relatorio de fatos (brief 3.4)."""

    __tablename__ = "facts"
    __table_args__ = (Index("ix_facts_video_conf", "video_id", "confidence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    #  Cresce a cada rodada de reescrita do gate; a ultima e a que vale.
    revision: Mapped[int] = mapped_column(Integer, default=1)

    claim_id: Mapped[str] = mapped_column(String(32))
    claim: Mapped[str] = mapped_column(Text)
    block_index: Mapped[int | None] = mapped_column(Integer, default=None)
    sources: Mapped[list[Any]] = mapped_column(JSON, default=list)
    confidence: Mapped[Confidence] = mapped_column(Enum(Confidence, native_enum=False))
    justification: Mapped[str | None] = mapped_column(Text, default=None)
    suggested_fix: Mapped[str | None] = mapped_column(Text, default=None)
    #  Resolvido por reescrita automatica ou por decisao humana.
    resolved_by: Mapped[str | None] = mapped_column(String(32), default=None)

    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    video: Mapped[Video] = relationship(back_populates="facts")


class CostEntry(Base):
    """Uma chamada registrada. Nenhuma chamada paga acontece sem uma destas (ADR 0003)."""

    __tablename__ = "cost_entries"
    __table_args__ = (
        Index("ix_cost_mes", "month_key"),
        Index("ix_cost_video_step", "video_id", "step"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    #  "2026-09" — mes de calendario em UTC (ADR 0003).
    month_key: Mapped[str] = mapped_column(String(7), index=True)

    step: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(128))
    unit: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[float] = mapped_column(Float, default=0.0)
    #  Detalhe da unidade: tokens de entrada e saida, numero de imagens etc.
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    #  Provedor local: registrado com custo zero para medir volume.
    local: Mapped[bool] = mapped_column(Boolean, default=False)

    video_id: Mapped[str | None] = mapped_column(
        ForeignKey("videos.id", ondelete="SET NULL"), default=None, index=True
    )
    step_run_id: Mapped[int | None] = mapped_column(Integer, default=None)

    video: Mapped[Video | None] = relationship(back_populates="costs")


# --------------------------------------------------------------------------
# Livros
# --------------------------------------------------------------------------


class Book(Base):
    """Livro ingerido: metadados, classificacao de direitos e capitulos."""

    __tablename__ = "books"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[str] = mapped_column(Text)
    format: Mapped[str] = mapped_column(String(8))  # pdf | epub
    sha256: Mapped[str] = mapped_column(String(64), index=True)

    title: Mapped[str | None] = mapped_column(Text, default=None)
    subtitle: Mapped[str | None] = mapped_column(Text, default=None)
    author: Mapped[str | None] = mapped_column(Text, default=None)
    author_death_year: Mapped[int | None] = mapped_column(Integer, default=None)
    translator: Mapped[str | None] = mapped_column(Text, default=None)
    translator_death_year: Mapped[int | None] = mapped_column(Integer, default=None)
    language: Mapped[str | None] = mapped_column(String(8), default=None)
    original_year: Mapped[int | None] = mapped_column(Integer, default=None)
    edition_year: Mapped[int | None] = mapped_column(Integer, default=None)
    publisher: Mapped[str | None] = mapped_column(Text, default=None)

    chapters: Mapped[list[Any]] = mapped_column(JSON, default=list)
    #  OCR foi necessario? Muda a confianca no texto extraido.
    ocr_used: Mapped[bool] = mapped_column(Boolean, default=False)

    rights_status: Mapped[RightsStatus] = mapped_column(
        Enum(RightsStatus, native_enum=False), default=RightsStatus.NAO_CLASSIFICADA
    )
    #  Justificativa registrada junto com a classificacao (brief 4.2).
    rights_reason: Mapped[str | None] = mapped_column(Text, default=None)
    rights_detail: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    rights_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)

    ingested_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    chunks: Mapped[list[BookChunk]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )
    videos: Mapped[list[Video]] = relationship(back_populates="book")

    @property
    def can_be_adapted(self) -> bool:
        """So obra livre pode ser adaptada ou narrada (brief 4.2)."""
        return self.rights_status is RightsStatus.LIVRE


class BookChunk(Base):
    """Trecho indexado de um livro. Alimenta a busca vetorial e a checagem."""

    __tablename__ = "book_chunks"
    __table_args__ = (Index("ix_chunk_book_chapter", "book_id", "chapter"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"), index=True)
    chapter: Mapped[int | None] = mapped_column(Integer, default=None)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer, default=None)
    #  float32 cru; a busca e cosseno com NumPy (ADR 0001).
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, default=None)
    embedding_model: Mapped[str | None] = mapped_column(String(64), default=None)

    book: Mapped[Book] = relationship(back_populates="chunks")
