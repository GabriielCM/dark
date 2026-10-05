"""Grade de revisao das imagens (fase C): a primeira revisao humana.

O revisor ve todas as imagens do video na pagina da producao, por capitulo,
e aprova todas ou marca uma a uma para refazer:
- com um link, a foto vira a base do img2img daquela imagem. Se for do
  Commons, a licenca e conferida como na etapa de referencias (ADR 0006) e
  uma licenca recusada recusa o pedido. Se for de outro site, entra marcada
  como "licenca nao verificada", e o checklist do pacote avisa;
- com um motivo, o pedido fica para a sessao do Claude Code, que le a imagem
  e reescreve a descricao (`mundoantigo imagens descrever`).

Ciclo de um pedido (`revisao_imagens/pedidos.json`):

    rascunho -> pendente -> (em_andamento) -> aplicado | recusado
                    \\-> resolvido (o Claude reescreveu) -/
    pendente -> cancelado (o revisor desistiu)

Pedido so com link vai para o worker (`responsavel: worker`), que aplica
sozinho entre etapas. Com motivo, vai para o Claude. Aplicar arquiva a imagem
antiga em `revisao_imagens/anteriores/`, conta mais uma refacao no
storyboard (a semente muda, senao sairia a mesma imagem) e o runner devolve a
etapa assets para a fila (`Runner.redo_images`): ela gera so o que falta.

O arquivo de pedidos e escrito pelo painel, pelo worker e pela CLI: toda
escrita passa por `locked_update` (trava + troca atomica).
"""

from __future__ import annotations

import io
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import httpx
from PIL import Image, UnidentifiedImageError

from ..artifacts import ArtifactStore
from ..artifacts.jsonfile import file_lock, locked_update, read_json_or
from ..providers.references.base import ReferenceProvider
from ..providers.references.commons import commons_file
from ..references.licensing import classify

STAGE = "revisao_imagens"
REQUESTS = "pedidos.json"
PREVIOUS_DIR = "anteriores"
#  Link de outro site: limite de tamanho e lado maior salvo.
MAX_LINK_BYTES = 25 * 1024 * 1024
LINK_MAX_SIDE = 2048
USER_AGENT = "MundoAntigoPainel/0.3 (revisao de imagens)"

#  Pedidos que ainda nao terminaram: impedem a aprovacao da grade.
OPEN_STATES = ("rascunho", "pendente", "em_andamento", "resolvido")
#  Poses derivadas de outra (style/character.py): refazer a origem refaz elas.
DERIVED_FROM = {"apontando": ("joinha",)}

_KEY = re.compile(r"^(?:cena-(\d{3})(?:-peca-(\d+))?|thumb|mc-([a-z_]+))$")


class ReviewError(ValueError):
    """Pedido que nao pode ser atendido. A mensagem vai para o revisor."""


class SubmitError(ReviewError):
    """Envio recusado: um ou mais cartoes marcados estao incompletos."""

    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("; ".join(f"{key}: {msg}" for key, msg in errors.items()))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class Target:
    """Uma imagem da grade e onde ficam os arquivos dela."""

    key: str
    kind: str  # "cena", "peca" (peca de cartao), "thumb" ou "mc" (pose do MC)
    scene: int | None
    piece: int | None
    image: Path
    reference: Path
    white: Path | None
    pose: str | None = None


def target(store: ArtifactStore, key: str) -> Target:
    match = _KEY.match(key.strip())
    if not match:
        raise ReviewError(f"imagem desconhecida: {key!r}")
    key = key.strip()
    if key == "thumb":
        return Target(
            "thumb",
            "thumb",
            None,
            None,
            store.path("assets", "thumb-base.png"),
            store.path("referencias", "thumb.jpg"),
            None,
        )
    if match.group(3):
        pose = match.group(3)
        return Target(
            key,
            "mc",
            None,
            None,
            store.path("assets", f"mc/{pose}.png"),
            store.path("referencias", f"mc-{pose}.jpg"),
            None,
            pose=pose,
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


def requests_file(store: ArtifactStore) -> Path:
    return store.path(STAGE, REQUESTS)


def load_requests(store: ArtifactStore) -> list[dict[str, Any]]:
    data = read_json_or(requests_file(store), {"pedidos": []})
    return list(data.get("pedidos", [])) if isinstance(data, dict) else []


def _update(store: ArtifactStore, change: Any) -> Any:
    def apply(data: dict[str, Any]) -> Any:
        requests = data.setdefault("pedidos", [])
        return change(requests)

    return locked_update(requests_file(store), apply, {"pedidos": []})


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _next_id(requests: list[dict[str, Any]]) -> int:
    return max((int(r.get("id", 0)) for r in requests), default=0) + 1


def _clean(text: str | None) -> str | None:
    return " ".join((text or "").split()) or None


def _link_error(link: str | None, chosen: Target) -> str | None:
    if not link:
        return None
    if chosen.kind == "mc":
        return "pose do MC nao usa foto de referencia: explique o motivo"
    parsed = urlparse(link)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "o link precisa comecar com http:// ou https://"
    return None


def save_draft(
    store: ArtifactStore,
    key: str,
    *,
    redo: bool,
    link: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    """Salva o que o revisor esta preenchendo num cartao (salvamento automatico).

    Desmarcar "refazer" apaga o rascunho. Um cartao com pedido ja enviado e
    ainda aberto nao aceita rascunho novo.
    """
    chosen = target(store, key)
    link = (link or "").strip() or None
    reason = (reason or "").strip() or None

    def change(requests: list[dict[str, Any]]) -> dict[str, Any] | None:
        open_sent = [
            r
            for r in requests
            if r.get("alvo") == chosen.key
            and r.get("estado") in ("pendente", "em_andamento", "resolvido")
        ]
        if open_sent:
            raise ReviewError("esta imagem ja tem um pedido em andamento")
        drafts = [
            r for r in requests if r.get("alvo") == chosen.key and r.get("estado") == "rascunho"
        ]
        if not redo:
            for draft in drafts:
                requests.remove(draft)
            return None
        if drafts:
            draft = drafts[-1]
        else:
            draft = {
                "id": _next_id(requests),
                "alvo": chosen.key,
                "estado": "rascunho",
                "origem": "revisor",
                "criado_em": _now(),
            }
            requests.append(draft)
        draft.update({"link": link, "motivo": reason, "atualizado_em": _now()})
        return dict(draft)

    result: dict[str, Any] | None = _update(store, change)
    return result


def drafts(store: ArtifactStore) -> list[dict[str, Any]]:
    return [r for r in load_requests(store) if r.get("estado") == "rascunho"]


def submit(store: ArtifactStore) -> dict[str, int]:
    """Transforma os rascunhos em pedidos. Tudo ou nada: um cartao incompleto barra o envio.

    Devolve quantos pedidos vao para o worker (so link) e para o Claude (motivo).
    """

    def change(requests: list[dict[str, Any]]) -> dict[str, int]:
        pending_drafts = [r for r in requests if r.get("estado") == "rascunho"]
        errors: dict[str, str] = {}
        for draft in pending_drafts:
            chosen = target(store, draft["alvo"])
            if not draft.get("link") and not draft.get("motivo"):
                errors[chosen.key] = "cole um link de referencia ou explique o motivo"
                continue
            problem = _link_error(draft.get("link"), chosen)
            if problem:
                errors[chosen.key] = problem
        if errors:
            raise SubmitError(errors)
        counts = {"worker": 0, "claude": 0}
        for draft in pending_drafts:
            chosen = target(store, draft["alvo"])
            has_link, has_reason = bool(draft.get("link")), bool(draft.get("motivo"))
            draft["tipo"] = (
                "link+motivo" if has_link and has_reason else ("link" if has_link else "motivo")
            )
            owner = "worker" if has_link and not has_reason and chosen.kind != "mc" else "claude"
            draft["responsavel"] = owner
            draft["estado"] = "pendente"
            draft["enviado_em"] = _now()
            draft["atualizado_em"] = draft["enviado_em"]
            counts[owner] += 1
        return counts

    result: dict[str, int] = _update(store, change)
    return result


def _find(requests: list[dict[str, Any]], request_id: int) -> dict[str, Any]:
    for entry in requests:
        if int(entry.get("id", 0)) == request_id:
            return entry
    raise ReviewError(f"pedido {request_id} nao existe")


def cancel(store: ArtifactStore, request_id: int) -> dict[str, Any]:
    """O revisor desiste de um pedido enviado que ainda nao foi aplicado."""

    def change(requests: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(requests, request_id)
        if entry.get("estado") not in ("pendente", "resolvido"):
            raise ReviewError(f"o pedido {request_id} ja esta {entry.get('estado')}")
        entry["estado"] = "cancelado"
        entry["atualizado_em"] = _now()
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def claude_pending(store: ArtifactStore) -> list[dict[str, Any]]:
    """Pedidos que esperam a sessao do Claude: tem motivo, ou sao pose do MC."""
    return [
        r
        for r in load_requests(store)
        if r.get("estado") == "pendente" and r.get("responsavel") == "claude"
    ]


def mark_seen(store: ArtifactStore) -> int:
    """A sessao viu os pedidos dela: a pagina mostra "visto pelo Claude"."""

    def change(requests: list[dict[str, Any]]) -> int:
        seen = 0
        for entry in requests:
            if (
                entry.get("estado") == "pendente"
                and entry.get("responsavel") == "claude"
                and not entry.get("visto_pelo_claude_em")
            ):
                entry["visto_pelo_claude_em"] = _now()
                seen += 1
        return seen

    result: int = _update(store, change)
    return result


def _claude_request(
    requests: list[dict[str, Any]], key: str, request_id: int | None
) -> dict[str, Any] | None:
    if request_id is not None:
        return _find(requests, request_id)
    for entry in reversed(requests):
        if (
            entry.get("alvo") == key
            and entry.get("estado") == "pendente"
            and entry.get("responsavel") == "claude"
        ):
            return entry
    return None


def describe(
    store: ArtifactStore,
    key: str,
    text: str,
    *,
    request_id: int | None = None,
    reply: str | None = None,
) -> dict[str, Any]:
    """A sessao reescreveu a descricao: o pedido fica pronto para aplicar.

    Sem pedido do revisor (o Claude achou o problema sozinho), cria um.
    """
    chosen = target(store, key)
    if chosen.kind == "mc":
        raise ReviewError("pose do MC: use `imagens refazer` (semente nova, mesmo figurino)")
    description = _clean(text)
    if not description:
        raise ReviewError("a descricao nova esta vazia")

    def change(requests: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _claude_request(requests, chosen.key, request_id)
        if entry is None:
            entry = {
                "id": _next_id(requests),
                "alvo": chosen.key,
                "origem": "claude",
                "tipo": "motivo",
                "responsavel": "claude",
                "criado_em": _now(),
            }
            requests.append(entry)
        entry.update(
            {
                "estado": "resolvido",
                "descricao_nova": description,
                "resposta": _clean(reply),
                "resolvido_em": _now(),
                "atualizado_em": _now(),
            }
        )
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def redo_without_change(
    store: ArtifactStore,
    key: str,
    *,
    request_id: int | None = None,
    reply: str | None = None,
) -> dict[str, Any]:
    """Refazer com semente nova e a mesma descricao (pose do MC, imagem azarada)."""
    chosen = target(store, key)

    def change(requests: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _claude_request(requests, chosen.key, request_id)
        if entry is None:
            entry = {
                "id": _next_id(requests),
                "alvo": chosen.key,
                "origem": "claude",
                "tipo": "motivo",
                "responsavel": "claude",
                "criado_em": _now(),
            }
            requests.append(entry)
        entry.update(
            {
                "estado": "resolvido",
                "resposta": _clean(reply),
                "resolvido_em": _now(),
                "atualizado_em": _now(),
            }
        )
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def refuse(store: ArtifactStore, request_id: int, reply: str) -> dict[str, Any]:
    """A sessao nao vai refazer: explica o porque ao revisor."""

    def change(requests: list[dict[str, Any]]) -> dict[str, Any]:
        entry = _find(requests, request_id)
        entry["estado"] = "recusado"
        entry["resposta"] = _clean(reply)
        entry["atualizado_em"] = _now()
        return dict(entry)

    result: dict[str, Any] = _update(store, change)
    return result


def outstanding(store: ArtifactStore) -> list[dict[str, Any]]:
    """Rascunhos e pedidos que ainda nao terminaram."""
    return [r for r in load_requests(store) if r.get("estado") in OPEN_STATES]


def can_approve(store: ArtifactStore) -> tuple[bool, str]:
    """A grade pode ser aprovada? Nao com pedido aberto ou imagem faltando."""
    pending_requests = outstanding(store)
    if pending_requests:
        drafts_count = sum(1 for r in pending_requests if r.get("estado") == "rascunho")
        if drafts_count:
            return False, f"{drafts_count} imagem(ns) marcada(s) para refazer ainda nao enviada(s)"
        return False, f"{len(pending_requests)} pedido(s) de refacao em andamento"
    missing = [item["chave"] for item in grid(store) if not item["existe"]]
    if missing:
        return False, f"{len(missing)} imagem(ns) ainda sendo gerada(s)"
    return True, ""


# -- storyboard --------------------------------------------------------------


def _storyboard_path(store: ArtifactStore) -> Path:
    return store.path("cenas", "storyboard.json")


def _node(storyboard: dict[str, Any], chosen: Target) -> dict[str, Any]:
    """O trecho do storyboard que descreve a imagem."""
    if chosen.kind == "thumb":
        node = storyboard.get("thumbnail")
        if not isinstance(node, dict):
            raise ReviewError("o storyboard nao tem thumbnail")
        return node
    if chosen.kind == "mc":
        character = storyboard.get("personagem")
        if not isinstance(character, dict):
            raise ReviewError("o storyboard nao tem o MC")
        return character
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


def redo_count(node: dict[str, Any], chosen: Target) -> int:
    if chosen.kind == "mc":
        return int((node.get("refacoes_poses") or {}).get(chosen.pose or "", 0))
    return int(node.get("refacoes") or 0)


def bump(
    store: ArtifactStore,
    chosen: Target,
    *,
    description: str | None = None,
    reference_link: str | None = None,
) -> int:
    """Conta mais uma refacao da imagem (semente nova) e troca a descricao, se veio.

    Com link do revisor, a imagem passa a usar a foto dele como referencia.
    Chame dentro de `file_lock` do storyboard.
    """
    path = _storyboard_path(store)
    storyboard = store.read_json("cenas", "storyboard.json")
    node = _node(storyboard, chosen)
    if chosen.kind == "mc":
        poses = dict(node.get("refacoes_poses") or {})
        poses[chosen.pose or ""] = int(poses.get(chosen.pose or "", 0)) + 1
        node["refacoes_poses"] = poses
        count = poses[chosen.pose or ""]
    else:
        node["refacoes"] = int(node.get("refacoes") or 0) + 1
        count = int(node["refacoes"])
        if description:
            node[description_field(chosen)] = " ".join(description.split())
            node["descricao_da_sessao"] = True
        if reference_link:
            node["referencia"] = {
                "busca": None,
                "alvo": node.get(description_field(chosen)),
                "origem": "revisor",
                "link": reference_link,
            }
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
    return count


def archive(store: ArtifactStore, chosen: Target, version: int) -> str | None:
    """Tira a imagem da pasta assets e guarda como versao anterior.

    A etapa assets gera o que falta; a grade mostra antes e depois. O recorte
    em branco da foto antiga vai embora, porque depende dela. Pose do MC leva
    junto a bruta (e as poses derivadas dela) e o indice do conjunto.
    """
    previous_dir = store.stage(STAGE) / PREVIOUS_DIR
    previous_dir.mkdir(parents=True, exist_ok=True)
    kept: str | None = None
    if chosen.image.exists():
        destination = previous_dir / f"{chosen.key}.r{version}.png"
        shutil.move(str(chosen.image), destination)
        kept = destination.relative_to(store.root).as_posix()
    store.sidecar_path(chosen.image).unlink(missing_ok=True)
    if chosen.white is not None:
        store.delete(chosen.white)
    if chosen.kind == "mc" and chosen.pose:
        folder = store.stage("assets") / "mc"
        for pose in (chosen.pose, *DERIVED_FROM.get(chosen.pose, ())):
            (folder / "brutas" / f"{pose}.png").unlink(missing_ok=True)
            if pose != chosen.pose:
                store.delete(folder / f"{pose}.png")
        store.delete(folder / "index.json")
    return kept


# -- aplicar -----------------------------------------------------------------


@dataclass
class ApplyReport:
    applied: list[str] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.applied)


def _finish(store: ArtifactStore, request_id: int, **fields: Any) -> None:
    def change(requests: list[dict[str, Any]]) -> None:
        entry = _find(requests, request_id)
        entry.update(fields)
        entry["atualizado_em"] = _now()

    _update(store, change)


async def apply(
    store: ArtifactStore,
    references: ReferenceProvider,
    *,
    include_claude: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> ApplyReport:
    """Aplica os pedidos prontos: baixa a foto do link, arquiva a imagem, conta a refacao.

    Pronto e: pedido so de link enviado (worker) ou pedido que o Claude ja
    resolveu. Quem chama devolve a etapa assets para a fila uma vez, no fim
    (`Runner.redo_images`), e so quando a etapa nao esta rodando.
    """

    def claim(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        chosen: list[dict[str, Any]] = []
        for entry in requests:
            ready = (
                entry.get("estado") == "pendente" and entry.get("responsavel") == "worker"
            ) or (include_claude and entry.get("estado") == "resolvido")
            if ready:
                entry["estado"] = "em_andamento"
                entry["atualizado_em"] = _now()
                chosen.append(dict(entry))
        return chosen

    batch: list[dict[str, Any]] = _update(store, claim)
    report = ApplyReport()
    for entry in batch:
        request_id = int(entry["id"])
        key = str(entry["alvo"])
        try:
            chosen = target(store, key)
            provenance: dict[str, Any] | None = None
            link = entry.get("link")
            if link:
                provenance = await reference_from_link(
                    link,
                    chosen.reference,
                    references=references,
                    video_id=store.video_id,
                    transport=transport,
                )
                store.write_sidecar(chosen.reference, step=STAGE, extra={"referencia": provenance})
            with file_lock(_storyboard_path(store)):
                storyboard = store.read_json("cenas", "storyboard.json")
                version = redo_count(_node(storyboard, chosen), chosen)
                previous = archive(store, chosen, version)
                count = bump(
                    store,
                    chosen,
                    description=entry.get("descricao_nova"),
                    reference_link=link,
                )
        except ReviewError as exc:
            _finish(store, request_id, estado="recusado", detalhe=str(exc))
            report.refused.append((key, str(exc)))
            continue
        _finish(
            store,
            request_id,
            estado="aplicado",
            aplicado_em=_now(),
            refacao=count,
            anterior=previous,
            referencia=provenance,
        )
        report.applied.append(key)
    return report


def has_ready_requests(store: ArtifactStore, *, include_claude: bool = True) -> bool:
    for entry in load_requests(store):
        if entry.get("estado") == "pendente" and entry.get("responsavel") == "worker":
            return True
        if include_claude and entry.get("estado") == "resolvido":
            return True
    return False


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


def _stamp(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return 0.0


def card_state(item: dict[str, Any], request: dict[str, Any] | None) -> str:
    """Estado do cartao na grade, a partir do ultimo pedido daquela imagem."""
    if request is None or request.get("estado") == "cancelado":
        return "ok"
    state = str(request.get("estado"))
    if state == "rascunho":
        return "rascunho"
    if state == "em_andamento" or (state == "pendente" and request.get("responsavel") == "worker"):
        return "enviado"
    if state == "pendente":
        return "aguardando_claude"
    if state == "resolvido":
        return "pronto_para_refazer"
    if state == "aplicado":
        fresh = item["existe"] and item["mtime"] >= _stamp(request.get("aplicado_em"))
        return "refeita" if fresh else "refazendo"
    if state == "recusado":
        return "recusado"
    return "ok"


def _item(
    store: ArtifactStore,
    chosen: Target,
    node: dict[str, Any],
    *,
    requests: dict[str, dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    exists = chosen.image.exists()
    mtime = chosen.image.stat().st_mtime if exists else 0.0
    request = requests.get(chosen.key)
    previous_dir = store.root / STAGE / PREVIOUS_DIR
    previous = sorted(previous_dir.glob(f"{chosen.key}.r*.png")) if previous_dir.is_dir() else []
    item = {
        "chave": chosen.key,
        "tipo_imagem": chosen.kind,
        "imagem": chosen.image.relative_to(store.root).as_posix(),
        "existe": exists,
        "mtime": mtime,
        "versao": int(mtime),
        "descricao": node.get(description_field(chosen)) if chosen.kind != "mc" else None,
        "refacoes": redo_count(node, chosen),
        "referencia": _provenance(store, chosen),
        "pedido": request,
        "anterior": previous[-1].relative_to(store.root).as_posix() if previous else None,
        **extra,
    }
    item["estado"] = card_state(item, request)
    return item


def _latest_requests(store: ArtifactStore) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in load_requests(store):
        latest[str(entry.get("alvo"))] = entry
    return latest


def _poses(store: ArtifactStore, storyboard: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for scene in storyboard.get("cenas", []):
        pose = (scene.get("mc") or {}).get("pose")
        if pose and pose not in seen:
            seen.append(pose)
    folder = store.root / "assets" / "mc"
    if folder.is_dir():
        for image in sorted(folder.glob("*.png")):
            if image.stem not in seen:
                seen.append(image.stem)
    return seen


def grid(store: ArtifactStore) -> list[dict[str, Any]]:
    """Todas as imagens do video, na ordem em que aparecem, com o contexto de cada uma.

    Primeiro a arte da thumbnail e as poses do MC; depois as cenas (ou as
    pecas de cada cartao), com o capitulo em que estao.
    """
    if not _storyboard_path(store).exists():
        return []
    storyboard = store.read_json("cenas", "storyboard.json")
    latest = _latest_requests(store)
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
                capitulo=None,
                narracao=thumbnail.get("conceito"),
            )
        )
    character = storyboard.get("personagem") or {}
    usage: dict[str, int] = {}
    for scene in storyboard.get("cenas", []):
        pose = (scene.get("mc") or {}).get("pose")
        if pose:
            usage[pose] = usage.get(pose, 0) + 1
    for pose in _poses(store, storyboard):
        times = usage.get(pose, 0)
        items.append(
            _item(
                store,
                target(store, f"mc-{pose}"),
                character,
                requests=latest,
                cena=None,
                tipo="mc",
                capitulo=None,
                narracao=f"MC recortado, pose {pose.replace('_', ' ')}"
                + (f" (usada em {times} cena{'s' if times != 1 else ''})" if times else ""),
            )
        )
    chapter: str | None = None
    for scene in storyboard.get("cenas", []):
        index = int(scene["indice"])
        title = (scene.get("titulo_capitulo") or {}).get("pt")
        if title:
            chapter = str(title)
        context = {
            "cena": index,
            "tipo": scene.get("tipo"),
            "capitulo": chapter,
            "narracao": scene.get("narracao"),
        }
        pieces = (scene.get("cartao") or {}).get("pecas") or []
        if scene.get("tipo") == "cartao" and pieces:
            for k, piece in enumerate(pieces, start=1):
                chosen = target(store, f"cena-{index:03d}-peca-{k}")
                items.append(_item(store, chosen, piece, requests=latest, **context))
        else:
            chosen = target(store, f"cena-{index:03d}")
            items.append(_item(store, chosen, scene, requests=latest, **context))
    return items


def sections(store: ArtifactStore) -> list[dict[str, Any]]:
    """A grade dividida para revisar: thumbnail e MC no topo, depois um bloco por capitulo."""
    items = grid(store)
    top = [i for i in items if i["tipo_imagem"] in ("thumb", "mc")]
    result: list[dict[str, Any]] = []
    if top:
        result.append({"id": "topo", "titulo": "Thumbnail e poses do MC", "itens": top})
    current: dict[str, Any] | None = None
    for item in items:
        if item["tipo_imagem"] in ("thumb", "mc"):
            continue
        title = item.get("capitulo") or "Abertura"
        if current is None or current["titulo"] != title:
            current = {"id": f"cap-{len(result)}", "titulo": title, "itens": []}
            result.append(current)
        current["itens"].append(item)
    for section in result:
        section["total"] = len(section["itens"])
        section["marcadas"] = sum(
            1
            for i in section["itens"]
            if i["estado"] in ("rascunho", "enviado", "aguardando_claude", "pronto_para_refazer")
        )
    return result


def reviewed_images(store: ArtifactStore) -> list[Path]:
    """O que a aprovacao cobre: cenas, pecas, a arte da thumb e as poses do MC."""
    assets = store.stage("assets")
    images = sorted(assets.glob("cena-*.png"))
    if (assets / "thumb-base.png").exists():
        images.append(assets / "thumb-base.png")
    images += sorted((assets / "mc").glob("*.png")) if (assets / "mc").is_dir() else []
    return images
