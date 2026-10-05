"""Enderecos da pagina da producao, para avisos, CLI e o lancador."""

from __future__ import annotations

from urllib.parse import quote

from ..config import Settings


def panel_base(settings: Settings) -> str:
    host = settings.panel.host
    #  0.0.0.0 escuta em todas as interfaces, mas nao e um endereco de navegador.
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"http://{host}:{settings.panel.port}"


def page_url(settings: Settings, video_id: str, step: str | None = None) -> str:
    """A pagina da producao, aberta direto na etapa (ou nas perguntas)."""
    url = f"{panel_base(settings)}/videos/{quote(video_id)}"
    if step:
        anchor = "perguntas" if step == "perguntas" else f"etapa-{step}"
        url += f"?abrir={quote(step)}#{anchor}"
    return url
