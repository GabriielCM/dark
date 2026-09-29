"""Etapa 14: montagem.

Remotion renderiza os dois videos a partir das mesmas cenas. Se o projeto Node
nao estiver disponivel, a etapa grava as props e para com motivo claro em vez
de falhar em silencio — as props ficam prontas para render manual.
"""

from __future__ import annotations

import json
from pathlib import Path

from ...paths import get_paths
from ...render import RemotionRenderer, VideoProps, props_from_storyboard
from ..context import StepContext, StepResult
from ..state import StepName
from .base import Step


class MontagemStep(Step):
    name = StepName.MONTAGEM

    def outputs(self, ctx: StepContext) -> list[Path]:
        return [
            ctx.store.path("montagem", "video.pt-br.mp4"),
            ctx.store.path("montagem", "video.en.mp4"),
        ]

    async def run(self, ctx: StepContext) -> StepResult:
        renderer = RemotionRenderer(ctx.settings.render)
        storyboard = ctx.store.read_json("cenas", "storyboard.json")
        character_library = self._character_library()

        rendered: list[str] = []
        warnings: list[str] = []
        prepared: list[tuple[str, VideoProps, Path]] = []
        for channel, script_stage, script_file in (
            (ctx.channel_pt, "roteiro", "roteiro.aprovado.json"),
            (ctx.channel_en, "adaptacao", "roteiro.en.json"),
        ):
            lang = channel.id
            script = ctx.store.read_json(script_stage, script_file)
            timings = ctx.store.read_json("narracao", f"tempos.{lang}.json")

            props = props_from_storyboard(
                video_id=ctx.video_id,
                language=channel.language,
                title=str(script.get("titulo_provisorio", ctx.topic)),
                storyboard=storyboard,
                timings=timings,
                narration_file=f"narracao/narracao.{lang}.wav",
                config=ctx.settings.render,
                palette=ctx.settings.style.palette,
                character_library=character_library,
            )
            props_file = ctx.store.path("montagem", f"props.{lang}.json")
            renderer.write_props(props, props_file)
            prepared.append((lang, props, props_file))

            pace = props.durationInSeconds / max(len(props.scenes), 1)
            if (
                not ctx.settings.scenes.seconds_min * 0.7
                <= pace
                <= ctx.settings.scenes.seconds_max * 1.5
            ):
                warnings.append(f"{lang}: ritmo de {pace:.0f} s por imagem")

        #  As props dos dois idiomas ficam prontas antes de qualquer render.
        #  Se o Remotion nao puder rodar, elas ainda servem para render manual —
        #  sair no meio deixaria so metade do trabalho no disco.
        available, reason = renderer.is_available()
        if not available:
            return StepResult.blocked(
                f"props geradas, mas o Remotion nao pode rodar: {reason}",
                props=[str(p) for _, _, p in prepared],
            )

        for lang, props, props_file in prepared:
            output = ctx.store.path("montagem", f"video.{lang}.mp4")
            result = await renderer.render(
                props,
                props_file,
                output,
                #  O diretorio do video vira o public/ do Remotion: os caminhos
                #  nas props sao relativos a ele.
                public_dir=ctx.store.root,
            )
            ctx.store.write_sidecar(
                output,
                step="montagem",
                provider="remotion",
                model=f"{ctx.settings.render.width}x{ctx.settings.render.height}@{ctx.settings.render.fps}",
                extra={
                    "idioma": lang,
                    "cenas": len(props.scenes),
                    "duracao_s": props.durationInSeconds,
                    "render_s": round(result.duration_s, 1),
                },
            )
            rendered.append(lang)

        summary = f"videos renderizados: {', '.join(rendered)}"
        if warnings:
            #  Nao bloqueia: o video existe e e assistivel. Mas o revisor
            #  precisa saber antes de aprovar (brief 3.5).
            summary += f" — atencao ao ritmo ({'; '.join(warnings)})"
        return StepResult.done(summary=summary, idiomas=rendered, avisos_ritmo=warnings)

    @staticmethod
    def _character_library() -> dict[str, str]:
        """Mapa pose -> caminho do SVG na biblioteca do personagem.

        Biblioteca gerada uma unica vez (brief, principio 1). Vazia enquanto o
        personagem nao for definido (brief 12) — as cenas simplesmente saem sem
        ele.
        """
        library = get_paths().character_library
        if not library.is_dir():
            return {}
        index = library / "index.json"
        if index.exists():
            try:
                data = json.loads(index.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except json.JSONDecodeError:
                pass
        return {svg.stem: f"personagem/{svg.name}" for svg in sorted(library.glob("*.svg"))}
