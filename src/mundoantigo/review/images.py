"""Grade de revisao das imagens (fase C2): a primeira revisao humana.

O revisor ve todas as imagens do video de uma vez, com o trecho da narracao
de cada uma, e aprova todas ou pede para refazer uma a uma:
- com um link, a foto vira a base do img2img daquela imagem. Se for do
  Commons, a licenca e conferida como na etapa de referencias (ADR 0006) e
  uma licenca recusada recusa o pedido. Se for de outro site, entra marcada
  como "licenca nao verificada", e o checklist do pacote avisa;
- com um motivo, o pedido fica pendente para a sessao do Claude Code, que
  reescreve a descricao da imagem (`mundoantigo imagens refazer`).

Refazer apaga so as imagens pedidas, conta mais uma refacao no storyboard
(a semente muda, senao sairia a mesma imagem) e devolve a etapa assets para
a fila: ela gera o que falta, e a grade volta a esperar.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from ..artifacts import ArtifactStore
from ..providers.references.base import ReferenceProvider
from ..providers.references.commons import commons_file
from ..references.licensing import classify

STAGE = "revisao_imagens"
REQUESTS = "pedidos.json"
#  Link de outro site: limite de tamanho e lado maior salvo.
MAX_LINK_BYTES = 25 * 1024 * 1024
LINK_MAX_SIDE = 2048
USER_AGENT = "MundoAntigoPainel/0.2 (revisao de imagens)"

_KEY = re.compile(r"^(?:cena-(\d{3})(?:-peca-(\d+))?|thumb)$")


class ReviewError(ValueError):
    """Pedido que nao pode ser atendido. A mensagem vai para o revisor."""


@dataclass(frozen=True, slots=True)
class Target:
    """Uma imagem da grade e onde ficam os arquivos dela."""

    key: str
    kind: str  # "cena", "peca" (peca de cartao) ou "thumb"
    scene: int | None
    piece: int | None
    image: Path
    reference: Path
    white: Path | None


def target(store: ArtifactStore, key: str) -> Target:
    match = _KEY.match(key.strip())
    if not match:
        raise ReviewError(f"imagem desconhecida: {key!r}")
    if key.strip() == "thumb":
        return Target(
            "thumb",
            "thumb",
            None,
            None,
            store.path("assets", "thumb-base.png"),
            store.path("referencias", "thumb.jpg"),
            None,
        )
    scene = int(match.group(1))
    piece = int(match.group(2)) if match.group(2) else None
    stem = f"cena-{scene:03d}" + (f"-peca-{piece}" if piece else "")
    return Target(
        stem,
        "peca" if piece else "cena",
        scene,
        piece,
        store.path("assets", f"{stem}.png"),
        store.path("referencias", f"{stem}.jpg"),
        store.path("referencias", f"{stem}-branco.png"),
    )


# -- pedidos -----------------------------------------------------------------


def load_requests(store: ArtifactStore) -> list[dict[str, Any]]:
    if not store.path(STAGE, REQUESTS).exists():
        return []
    data = store.read_json(STAGE, REQUESTS)
    return list(data.get("pedidos", [])) if isinstance(data, dict) else []


def _save_requests(store: ArtifactStore, requests: list[dict[str, Any]]) -> None:
    store.write_json(STAGE, REQUESTS, {"pedidos": requests}, step=STAGE)


def pending(store: ArtifactStore) -> list[dict[str, Any]]:
    return [r for r in load_requests(store) if r.get("estado") == "pendente"]


def add_request(
    store: ArtifactStore, key: str, *, link: str | None = None, reason: str | None = None
) -> dict[str, Any]:
    link = (link or "").strip() or None
    reason = (reason or "").strip() or None
    if not link and not reason:
        raise ReviewError("refazer pede um link de referencia ou o motivo")
    if link and not urlparse(link).scheme.startswith("http"):
        raise ReviewError(f"link invalido: {link!r}")
    chosen = target(store, key)
    requests = load_requests(store)
    entry: dict[str, Any] = {
        "id": max((int(r.get("id", 0)) for r in requests), default=0) + 1,
        "alvo": chosen.key,
        "tipo": "link" if link else "motivo",
        "link": link,
        "motivo": reason,
        "estado": "pendente",
        "em": datetime.now(UTC).isoformat(),
    }
    requests.append(entry)
    _save_requests(store, requests)
    return entry


def resolve(
    store: ArtifactStore, request_id: int, state: str, *, detail: str | None = None
) -> dict[str, Any]:
    requests = load_requests(store)
    for entry in requests:
        if int(entry.get("id", 0)) == request_id:
            entry["estado"] = state
            entry["detalhe"] = detail
            entry["resolvido_em"] = datetime.now(UTC).isoformat()
            _save_requests(store, requests)
            return entry
    raise ReviewError(f"pedido {request_id} nao existe")


# -- storyboard --------------------------------------------------------------


def _node(storyboard: dict[str, Any], chosen: Target) -> dict[str, Any]:
    """O trecho do storyboard que descreve a imagem."""
    if chosen.kind == "thumb":
        node = storyboard.get("thumbnail")
        if not isinstance(node, dict):
            raise ReviewError("o storyboard nao tem thumbnail")
        return node
    for scene in storyboard.get("cenas", []):
        if int(scene.get("indice", -1)) != chosen.scene:
            continue
        pieces = (scene.get("cartao") or {}).get("pecas") or []
        found: dict[str, Any] | None = (
            scene
            if chosen.piece is None
            else pieces[chosen.piece - 1]
            if 1 <= chosen.piece <= len(pieces)
            else None
        )
        if found is not None:
            return found
    raise ReviewError(f"{chosen.key} nao esta no storyboard")


def description_field(chosen: Target) -> str:
    return "descricao" if chosen.kind == "peca" else "descricao_visual"


def bump(store: ArtifactStore, chosen: Target, *, description: str | None = None) -> int:
    """Conta mais uma refacao da imagem (semente nova) e troca a descricao, se veio."""
    path = store.path("cenas", "storyboard.json")
    storyboard = store.read_json("cenas", "storyboard.json")
    node = _node(storyboard, chosen)
    node["refacoes"] = int(node.get("refacoes") or 0) + 1
    if description:
        node[description_field(chosen)] = " ".join(description.split())
        node["descricao_da_sessao"] = True
    sidecar = store.read_sidecar(path)
    store.write_json(
        "cenas",
        "storyboard.json",
        storyboard,
        step=sidecar.step if sidecar else "cenas",
        provider=sidecar.provider if sidecar else None,
        model=sidecar.model if sidecar else None,
        prompt_ref=sidecar.prompt_ref if sidecar else None,
        extra={**(sidecar.extra if sidecar else {}), "ajustado_na_revisao_de_imagens": True},
    )
    return int(node["refacoes"])


def discard(store: ArtifactStore, chosen: Target) -> list[Path]:
    """Apaga a imagem (e o recorte em branco da foto, que depende dela)."""
    removed = [p for p in (chosen.image, chosen.white) if p is not None and store.delete(p)]
    return removed


# -- links -------------------------------------------------------------------


async def _fetch(url: str, transport: httpx.AsyncBaseTransport | None) -> bytes:
    async with httpx.AsyncClient(
        headers={"User-Agent": USER_AGENT},
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        transport=transport,
    ) as client:
        try:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    raise ReviewError(f"o link respondeu {response.status_code}")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_LINK_BYTES:
                        raise ReviewError("a imagem do link passa de 25 MB")
                    chunks.append(chunk)
        except httpx.HTTPError as exc:
            raise ReviewError(f"nao consegui baixar o link: {exc}") from exc
    return b"".join(chunks)


async def reference_from_link(
    link: str,
    destination: Path,
    *,
    references: ReferenceProvider,
    video_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Baixa a foto do link para `destination` e devolve a procedencia."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    commons = commons_file(link)
    if commons is not None:
        candidate = await references.lookup(commons, step=STAGE, video_id=video_id)
        if candidate is None:
            raise ReviewError("o arquivo nao foi encontrado no Commons")
        verdict = classify(candidate.metadata)
        if not verdict.accepted:
            raise ReviewError(f"licenca recusada ({verdict.license}): {verdict.reason}")
        await references.download(candidate, destination)
        return {
            "fonte": "commons",
            "curid": candidate.curid,
            "titulo": candidate.title,
            "autor": verdict.author,
            "licenca": verdict.license,
            "licenca_url": verdict.license_url,
            "url": candidate.page_url,
            "atribuicao_exigida": verdict.attribution_required,
            "verificada": True,
            "link_do_revisor": link,
        }

    data = await _fetch(link, transport)
    try:
        with Image.open(io.BytesIO(data)) as image:
            rgb = image.convert("RGB")
    except (UnidentifiedImageError, OSError) as exc:
        raise ReviewError("o link nao e uma imagem") from exc
    rgb.thumbnail((LINK_MAX_SIDE, LINK_MAX_SIDE), Image.Resampling.LANCZOS)
    rgb.save(destination, "JPEG", quality=92)
    parsed = urlparse(link)
    return {
        "fonte": "link",
        "titulo": unquote(Path(parsed.path).name) or parsed.netloc,
        "autor": None,
        "licenca": None,
        "url": link,
        "verificada": False,
        "link_do_revisor": link,
    }


# -- grade -------------------------------------------------------------------


def _provenance(store: ArtifactStore, chosen: Target) -> dict[str, Any] | None:
    for path in (chosen.image, chosen.reference):
        sidecar = store.read_sidecar(path)
        if sidecar is not None and sidecar.extra.get("referencia"):
            return dict(sidecar.extra["referencia"])
    return None


def _item(
    store: ArtifactStore,
    chosen: Target,
    node: dict[str, Any],
    *,
    requests: dict[str, dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    exists = chosen.image.exists()
    return {
        "chave": chosen.key,
        "tipo_imagem": chosen.kind,
        "imagem": chosen.image.relative_to(store.root).as_posix(),
        "existe": exists,
        "versao": int(chosen.image.stat().st_mtime) if exists else 0,
        "descricao": node.get(description_field(chosen)),
        "refacoes": int(node.get("refacoes") or 0),
        "referencia": _provenance(store, chosen),
        "pedido": requests.get(chosen.key),
        **extra,
    }


def grid(store: ArtifactStore) -> list[dict[str, Any]]:
    """Todas as imagens do video, na ordem em que aparecem, com o contexto de cada uma."""
    if not store.path("cenas", "storyboard.json").exists():
        return []
    storyboard = store.read_json("cenas", "storyboard.json")
    latest = {r["alvo"]: r for r in load_requests(store)}
    items: list[dict[str, Any]] = []
    thumbnail = storyboard.get("thumbnail")
    if isinstance(thumbnail, dict):
        items.append(
            _item(
                store,
                target(store, "thumb"),
                thumbnail,
                requests=latest,
                cena=None,
                tipo="thumbnail",
                narracao=thumbnail.get("conceito"),
            )
        )
    for scene in storyboard.get("cenas", []):
        index = int(scene["indice"])
        context = {"cena": index, "tipo": scene.get("tipo"), "narracao": scene.get("narracao")}
        pieces = (scene.get("cartao") or {}).get("pecas") or []
        if scene.get("tipo") == "cartao" and pieces:
            for k, piece in enumerate(pieces, start=1):
                chosen = target(store, f"cena-{index:03d}-peca-{k}")
                items.append(_item(store, chosen, piece, requests=latest, **context))
        else:
            chosen = target(store, f"cena-{index:03d}")
            items.append(_item(store, chosen, scene, requests=latest, **context))
    return items


def reviewed_images(store: ArtifactStore) -> list[Path]:
    """O que a aprovacao cobre: cenas, pecas, a arte da thumb e as poses do MC."""
    assets = store.stage("assets")
    images = sorted(assets.glob("cena-*.png"))
    if (assets / "thumb-base.png").exists():
        images.append(assets / "thumb-base.png")
    images += sorted((assets / "mc").glob("*.png")) if (assets / "mc").is_dir() else []
    return images
