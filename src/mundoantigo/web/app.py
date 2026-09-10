"""Painel local.

Cinco telas e um usuario (ADR 0001): fila, producao, revisao do corte final,
custos e livros. Jinja2 + HTMX, sem segundo toolchain de build.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..config import Settings, get_settings
from ..costs import CostRecorder, PriceTable
from ..db.session import get_sessionmaker, init_db
from ..paths import get_paths
from ..pipeline import Runner
from ..providers import ProviderRegistry

log = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or get_settings()
    paths = get_paths()
    paths.ensure()
    init_db()

    sessions = get_sessionmaker()
    costs = CostRecorder(cfg.budget, PriceTable.from_yaml(), sessions)
    providers = ProviderRegistry(settings=cfg, costs=costs)
    runner = Runner.build(settings=cfg, providers=providers, session_factory=sessions)

    app = FastAPI(title="Mundo Antigo", docs_url=None, redoc_url=None)
    app.state.settings = cfg
    app.state.costs = costs
    app.state.runner = runner
    app.state.sessions = sessions
    app.state.providers = providers

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["moeda"] = lambda v: f"US$ {float(v or 0):.4f}"
    templates.env.filters["duracao"] = _format_duration
    app.state.templates = templates

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    #  Os artefatos ficam fora do pacote; sao servidos para o player da revisao.
    app.mount("/artefatos", StaticFiles(directory=str(paths.videos)), name="artefatos")

    if cfg.panel.auth_token:
        app.middleware("http")(_token_middleware(cfg.panel.auth_token))

    from .routes import books, queue, review
    from .routes import costs as costs_routes

    app.include_router(queue.router)
    app.include_router(review.router)
    app.include_router(costs_routes.router)
    app.include_router(books.router)

    @app.exception_handler(404)
    async def not_found(request: Request, _exc: Exception) -> Response:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"erro": "nao encontrado"}, status_code=404)
        return templates.TemplateResponse(
            request,
            "erro.html",
            {"codigo": 404, "mensagem": "Pagina nao encontrada"},
            status_code=404,
        )

    @app.get("/saude", response_class=JSONResponse)
    async def health() -> dict[str, Any]:
        status = costs.status()
        return {
            "ok": True,
            "mes": status.month,
            "gasto_usd": round(status.spent_usd, 4),
            "teto_usd": status.hard_limit_usd,
            "provedores": providers.describe(),
        }

    log.info("painel pronto em http://%s:%d", cfg.panel.host, cfg.panel.port)
    return app


CallNext = Callable[[Request], Awaitable[Response]]


def _token_middleware(token: str) -> Callable[[Request, CallNext], Awaitable[Response]]:
    """Autenticacao por token quando o painel sai da rede local.

    CLAUDE.md, Seguranca: fora de 127.0.0.1, autenticacao e obrigatoria. A
    configuracao ja recusa subir sem token nesse caso; isto e a checagem.
    """

    async def middleware(request: Request, call_next: CallNext) -> Response:
        if request.url.path in ("/saude",) or request.url.path.startswith("/static"):
            return await call_next(request)
        supplied = request.headers.get("x-painel-token") or request.cookies.get("painel_token")
        if supplied != token:
            if request.query_params.get("token") == token:
                response = await call_next(request)
                response.set_cookie("painel_token", token, httponly=True, samesite="strict")
                return response
            return HTMLResponse("<h1>401</h1><p>Token invalido.</p>", status_code=401)
        return await call_next(request)

    return middleware


def _format_duration(seconds: float | None) -> str:
    if not seconds:
        return "—"
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, rest = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def run() -> None:
    """Sobe o painel. Chamado por `mundoantigo painel`."""
    import uvicorn

    cfg = get_settings()
    uvicorn.run(
        "mundoantigo.web.app:create_app",
        factory=True,
        host=cfg.panel.host,
        port=cfg.panel.port,
        log_level="info",
    )
