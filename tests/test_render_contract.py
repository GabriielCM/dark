"""Contrato de props entre Python e Remotion (ADR 0001).

A fronteira entre os dois processos nao tem checagem de tipos. Este teste e a
checagem: se um lado ganhar um campo e o outro nao, ele falha.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from mundoantigo.config import RenderConfig
from mundoantigo.render import SceneProps, VideoProps
from mundoantigo.render.props import CardPiece, CardProps, HostProps, OverlayCue, SubtitleCue
from mundoantigo.render.remotion import props_from_storyboard, write_contract_snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]
TYPES_TS = REPO_ROOT / "render" / "src" / "types.ts"


def _ts_fields(type_name: str) -> set[str]:
    """Extrai os campos de um `type X = {...}` do types.ts.

    Simples de proposito: um parser de TypeScript aqui seria mais fragil que a
    regex, e o arquivo e escrito a mao num formato estavel.
    """
    source = TYPES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", source, re.DOTALL)
    assert match, f"tipo {type_name} nao encontrado em types.ts"
    return set(re.findall(r"^\s{2}(\w+)\??:", match.group(1), re.MULTILINE))


@pytest.mark.parametrize(
    ("model", "ts_name"),
    [
        (VideoProps, "VideoProps"),
        (SceneProps, "SceneProps"),
        (HostProps, "HostProps"),
        (CardProps, "CardProps"),
        (CardPiece, "CardPiece"),
        (OverlayCue, "OverlayCue"),
        (SubtitleCue, "SubtitleCue"),
    ],
)
def test_fields_match_between_python_and_typescript(model, ts_name: str) -> None:
    python_fields = set(model.model_fields)
    typescript_fields = _ts_fields(ts_name)
    assert python_fields == typescript_fields, (
        f"{ts_name} divergiu — so no Python: {python_fields - typescript_fields}, "
        f"so no TS: {typescript_fields - python_fields}"
    )


def test_camera_moves_match() -> None:
    source = TYPES_TS.read_text(encoding="utf-8")
    ts_moves = set(re.findall(r'\|?\s*"(zoom_in|zoom_out|pan_left|pan_right|estatica)"', source))
    from typing import get_args

    from mundoantigo.render.props import CameraMove

    assert ts_moves == set(get_args(CameraMove))


def test_overlay_kinds_match() -> None:
    """`gancho` e `fim` (cortes do TikTok, ADR 0010) existem dos dois lados."""
    source = TYPES_TS.read_text(encoding="utf-8")
    match = re.search(r"export type OverlayKind = (.*?);", source)
    assert match
    ts_kinds = set(re.findall(r'"(\w+)"', match.group(1)))
    from typing import get_args

    from mundoantigo.render.props import OverlayKind

    assert ts_kinds == set(get_args(OverlayKind))


def test_snapshot_file_is_written(tmp_path: Path) -> None:
    destination = write_contract_snapshot(tmp_path / "contrato.json")
    snapshot = json.loads(destination.read_text())
    assert set(snapshot) == {
        "VideoProps",
        "SceneProps",
        "HostProps",
        "CardProps",
        "CardPiece",
        "OverlayCue",
        "SubtitleCue",
    }
    assert "durationInSeconds" in snapshot["VideoProps"]


class TestPropsValidation:
    def test_zero_duration_scene_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="positiva"):
            SceneProps(index=1, background="a.png", start=0, duration=0)

    def test_duration_in_frames_rounds(self) -> None:
        props = VideoProps(
            videoId="v",
            language="pt-BR",
            title="t",
            fps=30,
            durationInSeconds=60.04,
            narration="n.wav",
            scenes=[],
        )
        assert props.duration_in_frames == 1801

    def test_serializes_to_json_the_remotion_can_read(self) -> None:
        props = VideoProps(
            videoId="v",
            language="pt-BR",
            title="t",
            durationInSeconds=9,
            narration="narracao/n.wav",
            scenes=[SceneProps(index=1, background="assets/c.png", start=0, duration=9)],
        )
        payload = json.loads(props.model_dump_json())
        #  O Remotion le exatamente estas chaves; nada de snake_case aqui.
        assert payload["videoId"] == "v"
        assert payload["scenes"][0]["background"] == "assets/c.png"
        assert payload["scenes"][0]["host"] is None
        assert payload["overlays"] == []


@pytest.mark.skipif(shutil.which("node") is None, reason="node nao instalado")
def test_typescript_side_agrees(tmp_path: Path) -> None:
    """Roda a verificacao do lado TS, se houver Node na maquina."""
    snapshot = write_contract_snapshot(tmp_path / "contrato.json")
    result = subprocess.run(
        ["node", "--experimental-strip-types", "scripts/contract.ts", str(snapshot)],
        cwd=REPO_ROOT / "render",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr or result.stdout


STORYBOARD = {
    "versao": 2,
    "cenas": [
        {
            "indice": 1,
            "bloco": 0,
            "frases": ["p0001"],
            "fracao_bloco": [0.0, 0.5],
            "tipo": "atuada",
            "camera": "zoom_in",
            "titulo_capitulo": {
                "pt": "Antes do sol: desmontar o mundo",
                "en": "Before sunrise: taking the world apart",
            },
            "tarja": {"pt": "ACAMPAMENTO ROMANO", "en": "ROMAN CAMP"},
            "balao": {"pt": "Todo mundo sabe seu papel.", "en": "Everyone knows their job."},
        },
        {
            "indice": 2,
            "bloco": 0,
            "frases": ["p0002"],
            "fracao_bloco": [0.5, 1.0],
            "tipo": "cartao",
            "camera": "estatica",
            "cartao": {
                "pecas": [{"descricao": "a pickaxe", "rotulo": {"pt": "DOLABRA", "en": "PICKAXE"}}],
                "comparacao": False,
            },
            "mc": {"pose": "joinha", "lado": "direita"},
            "balao": {"pt": "Serviu ontem, serve hoje.", "en": "Did the job yesterday."},
        },
    ],
}
TEMPOS = {
    "duracao_s": 14.0,
    "frases": [
        {"id": "p0001", "bloco": 0, "inicio": 0.3, "fim": 6.0},
        {"id": "p0002", "bloco": 0, "inicio": 6.4, "fim": 13.5},
    ],
    "blocos": [{"indice": 0, "inicio_s": 0.3, "fim_s": 13.5}],
}
POSES = {"joinha": {"arquivo": "joinha.png", "cabeca": [0.5, 0.06], "proporcao": 0.48}}


def _props(language: str, timings: dict[str, Any] | None = None) -> VideoProps:
    return props_from_storyboard(
        video_id="v",
        language=language,
        title="t",
        storyboard=STORYBOARD,
        timings=timings or TEMPOS,
        narration_file="narracao/n.wav",
        config=RenderConfig(
            fps=30, width=1920, height=1080, project="render", concurrency=1, crf=18
        ),
        palette={},
        poses=POSES,
        font_family="Comic Relief",
    )


class TestOverlaysFromStoryboard:
    def test_chapter_title_tag_and_balloon_on_the_first_scene(self) -> None:
        props = _props("pt-BR")
        kinds = [(c.kind, c.text) for c in props.overlays if c.start < 6.4]
        #  Na tela, so o trecho antes dos dois-pontos, como nas entregas.
        assert ("titulo", "Antes do sol") in kinds
        assert ("tarja", "ACAMPAMENTO ROMANO") in kinds
        balloon = next(c for c in props.overlays if c.text == "Todo mundo sabe seu papel.")
        #  Cena atuada, sem MC recortado: o rabicho aponta para o ponto padrao.
        assert balloon.scene is None and balloon.anchorX is not None

    def test_scene_cues_end_with_their_scene(self) -> None:
        """Balao e texto-chave nao atravessam para a cena seguinte (amostra de 30/09)."""
        short = {**TEMPOS, "frases": [dict(f) for f in TEMPOS["frases"]]}
        short["frases"][1]["inicio"] = 3.0  # a primeira cena dura 3 s
        props = _props("pt-BR", short)
        first_end = props.scenes[0].start + props.scenes[0].duration
        balloon = next(c for c in props.overlays if c.text == "Todo mundo sabe seu papel.")
        assert first_end == pytest.approx(3.0)
        assert balloon.start + balloon.duration <= first_end + 1e-6

    def test_card_scene_brings_pieces_host_and_the_previous_background(self) -> None:
        props = _props("pt-BR")
        card_scene = props.scenes[1]
        assert card_scene.card is not None
        assert card_scene.card.pieces[0].label == "DOLABRA"
        assert card_scene.background == "assets/cena-001.png"
        assert card_scene.host is not None and card_scene.host.aspect == 0.48
        balloon = next(c for c in props.overlays if c.kind == "balao" and c.scene == 2)
        assert balloon.text == "Serviu ontem, serve hoje."

    def test_english_props_carry_the_english_text(self) -> None:
        props = _props("en-US")
        texts = {c.text for c in props.overlays}
        assert {"Before sunrise", "ROMAN CAMP", "Did the job yesterday."} <= texts
        assert props.scenes[1].card is not None
        assert props.scenes[1].card.pieces[0].label == "PICKAXE"
        assert props.fontFamily == "Comic Relief"
