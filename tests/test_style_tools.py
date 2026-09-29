"""Ferramentas de estilo: calibracao contra a folha antiga e poses do MC."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mundoantigo.providers.image import FakeImage
from mundoantigo.style.calibration import Calibration, run_calibration
from mundoantigo.style.character import (
    POSES,
    cutout_white,
    generate_pose_set,
    head_anchor,
    pose_prompt,
    trim,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def calibration() -> Calibration:
    return Calibration.from_yaml(REPO_ROOT / "config" / "estilo" / "calibracao.yaml", REPO_ROOT)


class TestCalibration:
    def test_every_scene_of_the_old_sheet_is_listed(self, calibration: Calibration) -> None:
        assert len(calibration.scenes) == 24
        assert {s.sheet for s in calibration.scenes} == {1, 2, 3, 4}

    def test_prompt_carries_style_character_and_restrictions(self, calibration) -> None:
        scene = calibration.scenes[0]
        prompt = calibration.scene_prompt("a-contorno", scene)
        assert prompt.startswith(calibration.variants["a-contorno"])
        assert "full dark brown beard" in prompt
        assert "cream linen tunic" in prompt
        assert "No text" in prompt
        assert "{mc}" not in prompt

    def test_reference_crop_is_the_old_zimage_cell(self, calibration) -> None:
        crop = calibration.reference_crop(calibration.scenes[0])
        assert crop is not None
        assert crop.size == (200, 112)

    def test_unknown_variant_is_refused(self, calibration) -> None:
        with pytest.raises(ValueError, match="desconhecidas"):
            calibration.pick(["nao-existe"], None)

    async def test_builds_a_comparison_sheet(self, calibration, recorder, tmp_path) -> None:
        provider = FakeImage(costs=recorder)
        sheet = await run_calibration(
            calibration,
            provider,
            tmp_path,
            variants=["a-contorno", "b-sombreado"],
            scene_ids=["01", "09"],
            size=(64, 36),
        )
        assert sheet.exists()
        assert len(provider.calls) == 4
        assert {c.seed for c in provider.calls} == {11}
        logged = json.loads((tmp_path / "prompts.json").read_text(encoding="utf-8"))
        assert len(logged["itens"]) == 4

        #  Rodar de novo nao regera o que ja existe.
        await run_calibration(
            calibration,
            provider,
            tmp_path,
            variants=["a-contorno"],
            scene_ids=["01"],
            size=(64, 36),
        )
        assert len(provider.calls) == 4


def _figure(width: int = 200, height: int = 300) -> Image.Image:
    """Boneco de contorno grosso preto e corpo branco, em fundo branco."""
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((70, 20, 130, 80), fill="white", outline="black", width=6)  # cabeca
    draw.rectangle((60, 90, 140, 260), fill="white", outline="black", width=6)  # corpo
    #  Braco erguido acima da cabeca: e o caso que confunde a ancora.
    draw.line((140, 100, 190, 8), fill="black", width=8)
    return image


class TestCharacter:
    def test_white_background_is_removed_but_white_inside_is_kept(self) -> None:
        sprite = cutout_white(_figure())
        alpha = sprite.getchannel("A")
        assert alpha.getpixel((5, 5)) == 0  # fundo
        assert alpha.getpixel((100, 170)) == 255  # tunica branca dentro do contorno

    def test_trim_keeps_only_the_figure(self) -> None:
        sprite = trim(cutout_white(_figure()), padding=0)
        assert sprite.width < 200 and sprite.height < 300

    def test_head_anchor_ignores_the_raised_arm(self) -> None:
        cut = cutout_white(_figure())
        x0 = cut.getchannel("A").getbbox()[0]
        sprite = trim(cut, padding=0)
        x, y = head_anchor(sprite)
        #  Em pixels da imagem original: o centro da cabeca e x=100; a ponta do
        #  braco, que sobe mais alto, fica em x=190.
        assert abs(x0 + x * sprite.width - 100) < 12
        assert y < 0.2

    def test_pose_prompt_describes_the_pose_on_white(self) -> None:
        prompt = pose_prompt("estilo", "um romano", "capa preta", "joinha", "sem texto")
        assert POSES["joinha"] in prompt
        assert "pure white background" in prompt
        assert "capa preta" in prompt

    async def test_generates_the_pose_set_with_index(self, recorder, tmp_path) -> None:
        provider = FakeImage(costs=recorder)
        sprites = await generate_pose_set(
            provider,
            tmp_path,
            style="estilo",
            character="um romano",
            costume="capa preta",
            restrictions="sem texto",
            seed=11,
            poses=["joinha", "pensativo"],
        )
        assert [s.pose for s in sprites] == ["joinha", "pensativo"]
        assert {c.seed for c in provider.calls} == {11}
        index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
        assert set(index["poses"]) == {"joinha", "pensativo"}
        assert index["figurino"] == "capa preta"
