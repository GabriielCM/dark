"""Quem decide o que vira aviso e grava o evento.

Toda novidade de uma producao vira uma linha em `events`. So algumas viram
toast: as que precisam do revisor (uma etapa parou esperando por ele, falhou,
o orcamento travou, o Claude perguntou algo) e o "pacote pronto". O que o
proprio revisor fez na pagina, e a espera da sessao do Claude, ficam so no
registro.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from ..config import Settings
from ..db.models import Event, Video
from .base import Notice, Notifier

log = logging.getLogger(__name__)

#  Tipos que viram toast. O resto e so registro.
TOAST_KINDS = {"bloqueio", "falha", "orcamento", "pergunta", "pronto"}
#  Insistente: fica na tela ate ser fechado. "pronto" some sozinho.
QUIET_KINDS = {"pronto"}
#  Mesmo aviso de novo dentro disso (worker reiniciou, CLI repetida): so registro.
REPEAT_WINDOW = timedelta(minutes=10)


class Announcer:
    def __init__(
        self, sessions: sessionmaker[Session], notifier: Notifier, settings: Settings
    ) -> None:
        self.sessions = sessions
        self.notifier = notifier
        self.settings = settings

    def announce(
        self,
        video_id: str | None,
        kind: str,
        message: str,
        *,
        step: str | None = None,
        title: str | None = None,
    ) -> bool:
        """Registra o evento e mostra o aviso quando ele precisa do revisor.

        Devolve se o aviso foi mostrado. Nunca levanta excecao: um aviso nao
        pode parar o pipeline.
        """
        try:
            return self._announce(video_id, kind, message, step=step, title=title)
        except Exception:
            log.exception("nao consegui registrar o aviso (%s)", kind)
            return False

    def _announce(
        self,
        video_id: str | None,
        kind: str,
        message: str,
        *,
        step: str | None,
        title: str | None,
    ) -> bool:
        from ..web.links import page_url

        url = page_url(self.settings, video_id, step) if video_id else None
        since = datetime.now(UTC) - REPEAT_WINDOW
        with self.sessions() as s:
            topic = None
            if video_id:
                video = s.get(Video, video_id)
                topic = video.topic if video else None
            repeated = (
                s.query(Event)
                .filter(
                    Event.video_id == video_id,
                    Event.kind == kind,
                    Event.step == step,
                    Event.message == message,
                    Event.notified.is_(True),
                    Event.created_at > since,
                )
                .first()
                is not None
            )
            event = Event(video_id=video_id, kind=kind, step=step, message=message, url=url)
            s.add(event)
            s.commit()
            event_id = event.id

        if kind not in TOAST_KINDS or repeated:
            return False
        shown = self.notifier.send(
            Notice(
                title=title or (f"Mundo Antigo · {topic[:48]}" if topic else "Mundo Antigo"),
                body=message,
                url=url,
                kind=kind,
                video_id=video_id,
                insistent=kind not in QUIET_KINDS,
            )
        )
        if shown:
            with self.sessions() as s:
                stored = s.get(Event, event_id)
                if stored is not None:
                    stored.notified = True
                    s.commit()
        return shown


class NullAnnouncer:
    """Sem avisos nem registro: o runner do painel e os testes que nao ligam para isso."""

    def announce(
        self,
        video_id: str | None,
        kind: str,
        message: str,
        *,
        step: str | None = None,
        title: str | None = None,
    ) -> bool:
        return False
