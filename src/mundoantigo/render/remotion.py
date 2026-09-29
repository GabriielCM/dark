"""Ponte para o Remotion.

O Python nao importa nada de Node e o Remotion nao conhece o banco. O contrato
e um arquivo JSON e uma chamada de subprocesso (ADR 0001).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import RenderConfig
from ..errors import PermanentError, TransientError
from ..paths import get_paths
from .props import VideoProps

log = logging.getLogger(__name__)

#  Renderizar 15 minutos em 1080p pode passar de uma hora na 3060.
RENDER_TIMEOUT_S = 7200

#  O CLI e chamado pelo node, sem `npx`: no Windows o npx e um .cmd, que o
#  CreateProcess so executa via cmd.exe — e o cmd.exe reinterpreta os
#  argumentos (caminhos com espaco, `&`, `%`).
REMOTION_CLI = Path("node_modules") / "@remotion" / "cli" / "remotion-cli.js"


@dataclass(frozen=True, slots=True)
class RenderResult:
    output: Path
    duration_s: float
    props_file: Path


class RemotionRenderer:
    def __init__(self, config: RenderConfig, project_dir: Path | None = None) -> None:
        self.config = config
        self.project = project_dir or (get_paths().root / config.project)

    def is_available(self) -> tuple[bool, str]:
        """O Remotion pode rodar aqui? Devolve (pode, motivo se nao)."""
        if not self.project.is_dir():
            return False, f"projeto Remotion ausente em {self.project}"
        if not (self.project / REMOTION_CLI).is_file():
            return False, f"dependencias nao instaladas: rode `npm ci` em {self.project}"
        if shutil.which("node") is None:
            return False, "node nao encontrado no PATH (Node 22+ e necessario)"
        return True, ""

    def write_props(self, props: VideoProps, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            props.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
        )
        return destination

    async def render(
        self,
        props: VideoProps,
        props_file: Path,
        output: Path,
        *,
        composition: str = "Video",
        public_dir: Path | None = None,
    ) -> RenderResult:
        ok, reason = self.is_available()
        if not ok:
            raise PermanentError(f"nao da para renderizar: {reason}")

        self.write_props(props, props_file)
        output.parent.mkdir(parents=True, exist_ok=True)

        node = shutil.which("node")
        assert node is not None  # garantido por is_available()
        command = [
            node,
            str(REMOTION_CLI),
            "render",
            "src/index.ts",
            composition,
            str(output),
            f"--props={props_file}",
            f"--concurrency={self.config.concurrency}",
            f"--crf={self.config.crf}",
            "--log=warn",
        ]
        if public_dir is not None:
            #  E assim que o Remotion enxerga os PNGs e o WAV deste video sem
            #  que eles precisem ser copiados para dentro do projeto.
            command.append(f"--public-dir={public_dir}")

        log.info("renderizando %s -> %s", composition, output)
        started = asyncio.get_running_loop().time()
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=self.project,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout, stderr = await asyncio.wait_for(process.communicate(), RENDER_TIMEOUT_S)
        except TimeoutError as exc:
            process.kill()
            raise TransientError(
                f"render passou de {RENDER_TIMEOUT_S / 3600:.0f} h e foi interrompido"
            ) from exc

        elapsed = asyncio.get_running_loop().time() - started
        if process.returncode != 0:
            tail = (stderr or b"").decode(errors="replace")[-2000:]
            raise TransientError(f"remotion render falhou ({process.returncode}):\n{tail}")
        if not output.exists() or output.stat().st_size == 0:
            raise TransientError(f"remotion terminou sem gravar {output}")

        log.info("render concluido em %.1f s: %s", elapsed, output)
        return RenderResult(output=output, duration_s=elapsed, props_file=props_file)


#  Quanto tempo cada camada fica na tela (docs/estilo/analise-entregas.md).
TITLE_S = 10.0
TAG_S = 6.0
KEY_TEXT_S = 3.5
BALLOON_S = 3.8
#  Balao em cena atuada, sem MC recortado: o rabicho aponta para onde o MC
#  costuma estar nas cenas geradas (terco direito, altura da cabeca).
ACTED_ANCHOR = (0.62, 0.3)


def _text_for(value: Any, lang: str) -> str | None:
    if isinstance(value, dict):
        text = value.get(lang) or value.get("pt")
        return str(text) if text else None
    return None


def props_from_storyboard(
    *,
    video_id: str,
    language: str,
    title: str,
    storyboard: dict[str, Any],
    timings: dict[str, Any],
    narration_file: str,
    config: RenderConfig,
    palette: dict[str, str],
    poses: dict[str, Any] | None = None,
    font_family: str = "Comic Neue",
) -> VideoProps:
    """Monta as props a partir dos artefatos do pipeline.

    O tempo de cada cena vem da linha do tempo (scenes/timeline.py): no PT a
    cena comeca na propria frase, no EN na mesma fracao do bloco. As camadas
    saem no idioma do video; as imagens sao as mesmas nos dois.
    """
    from ..scenes.timeline import scene_times
    from .props import CardPiece, CardProps, HostProps, OverlayCue, SceneProps, SubtitleCue

    lang = "pt" if language.lower().startswith("pt") else "en"
    scenes_raw = storyboard.get("cenas", [])
    times = scene_times(scenes_raw, timings)
    total = times[-1][1] if times else float(timings.get("duracao_s") or 0.0)
    poses = poses or {}

    scenes: list[SceneProps] = []
    overlays: list[OverlayCue] = []
    last_background = ""

    def cue(kind: str, text: str | None, begin: float, length: float, **extra: Any) -> None:
        if text:
            overlays.append(
                OverlayCue(
                    kind=kind,  # type: ignore[arg-type]
                    start=round(begin, 3),
                    duration=round(max(1.2, min(length, total - begin)), 3),
                    text=text,
                    **extra,
                )
            )

    for raw, (start, end) in zip(scenes_raw, times, strict=True):
        index = int(raw["indice"])
        duration = max(0.5, round(end - start, 3))
        card = None
        if raw.get("tipo") == "cartao" and raw.get("cartao"):
            pieces = [
                CardPiece(
                    image=f"assets/cena-{index:03d}-peca-{k}.png",
                    label=_text_for(piece.get("rotulo"), lang) or "",
                )
                for k, piece in enumerate(raw["cartao"]["pecas"], start=1)
            ]
            card = CardProps(pieces=pieces, comparison=bool(raw["cartao"].get("comparacao")))
            #  Atras do papel aparece a cena anterior, desfocada.
            background = last_background or pieces[0].image
        else:
            background = f"assets/cena-{index:03d}.png"
            last_background = background

        host = None
        mc = raw.get("mc") or {}
        pose = mc.get("pose")
        if pose and pose in poses:
            entry = poses[pose]
            head = entry.get("cabeca") or [0.5, 0.06]
            host = HostProps(
                image=f"assets/mc/{entry.get('arquivo', pose + '.png')}",
                side=mc.get("lado") or "direita",
                aspect=float(entry.get("proporcao") or 0.5),
                headX=float(head[0]),
                headY=float(head[1]),
            )

        scenes.append(
            SceneProps(
                index=index,
                background=background,
                start=start,
                duration=duration,
                camera=str(raw.get("camera") or "estatica"),  # type: ignore[arg-type]
                kind=str(raw.get("tipo") or "lugar"),
                host=host,
                card=card,
            )
        )

        lead = min(0.8, duration * 0.3)
        cue("titulo", _text_for(raw.get("titulo_capitulo"), lang), start, TITLE_S)
        cue("tarja", _text_for(raw.get("tarja"), lang), start + lead / 2, TAG_S)
        cue("texto", _text_for(raw.get("texto_chave"), lang), start + lead, KEY_TEXT_S)
        balloon = _text_for(raw.get("balao"), lang)
        hold = min(BALLOON_S, duration)
        if host is not None:
            cue("balao", balloon, start + lead, hold, scene=index)
        else:
            cue(
                "balao",
                balloon,
                start + lead,
                hold,
                anchorX=ACTED_ANCHOR[0],
                anchorY=ACTED_ANCHOR[1],
            )

    subtitles = [
        SubtitleCue(start=float(w["i"]), end=float(w["f"]), text=str(w["p"]))
        for w in timings.get("palavras", [])
    ]
    return VideoProps(
        videoId=video_id,
        language=language,
        title=title,
        fps=config.fps,
        width=config.width,
        height=config.height,
        durationInSeconds=round(total, 3),
        narration=narration_file,
        scenes=scenes,
        overlays=overlays,
        subtitles=subtitles,
        palette=palette,
        fontFamily=font_family,
    )


def write_contract_snapshot(destination: Path) -> Path:
    """Grava os campos do contrato para o teste comparar com o lado TS."""
    from .props import CardPiece, CardProps, HostProps, OverlayCue, SceneProps, SubtitleCue

    snapshot = {
        "VideoProps": sorted(VideoProps.model_fields),
        "SceneProps": sorted(SceneProps.model_fields),
        "HostProps": sorted(HostProps.model_fields),
        "CardProps": sorted(CardProps.model_fields),
        "CardPiece": sorted(CardPiece.model_fields),
        "OverlayCue": sorted(OverlayCue.model_fields),
        "SubtitleCue": sorted(SubtitleCue.model_fields),
    }
    destination.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    return destination
