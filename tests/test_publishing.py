"""Publicacao (fase B8): descricao montada por codigo, limites do YouTube e
thumbnails, conferidos contra o pacote antigo (tests/fixtures/pacote_exemplo.txt)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageChops

from mundoantigo.config import ChannelConfig
from mundoantigo.errors import ConfigError
from mundoantigo.publishing import thumbnails
from mundoantigo.publishing.description import (
    Chapter,
    Credit,
    DescriptionParts,
    DescriptionTexts,
    SourceRef,
    chapters_from_timings,
    credits_from_provenance,
    format_credit,
    format_source,
    format_timestamp,
    render_description,
    shorten,
    sources_that_passed,
)
from mundoantigo.publishing.limits import (
    DESCRIPTION_MAX_BYTES,
    byte_length,
    fit_description,
    fit_tags,
    fit_title,
    tags_length,
    unaccented_pt,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (ROOT / "tests" / "fixtures" / "pacote_exemplo.txt").read_text(encoding="utf-8")


def channel(lang: str) -> ChannelConfig:
    return ChannelConfig.from_yaml(ROOT / "config" / "canais" / f"{lang}.yaml")


def texts(lang: str) -> DescriptionTexts:
    return DescriptionTexts.for_channel(channel(lang).publishing)


#  O video do concreto (EN, 17:56): blocos com o inicio real da primeira frase.
CONCRETE_BLOCKS = [
    {"indice": 0, "titulo": "An Empire Without a Harbor", "inicio_s": 0.42},
    {"indice": 1, "titulo": "Caesarea: When the Technique Fails", "inicio_s": 200.7},
    {
        "indice": 2,
        "titulo": "The Recipe That Works With the Sea, Not Against It",
        "inicio_s": 403.2,
    },
    {"indice": 3, "titulo": "The Price of Building With the Volcano", "inicio_s": 708.9},
    {"indice": 4, "titulo": "Nineteen Centuries Later, Still Standing", "inicio_s": 874.1},
]
PANTHEON = {
    "fonte": "commons",
    "curid": 145562084,
    "titulo": "Pantheon (Rome), Dome interior.jpg",
    "autor": "Wilfredor",
    "licenca": "CC0",
    "url": "https://commons.wikimedia.org/?curid=145562084",
    "verificada": True,
}
AMPHORA = {
    "fonte": "commons",
    "curid": 60407393,
    "titulo": "Terracotta amphora (storage jar) MET DP123.jpg",
    "autor": None,
    "licenca": "CC0",
    "url": "https://commons.wikimedia.org/?curid=60407393",
    "verificada": True,
}


class TestChapters:
    def test_same_timestamps_as_the_old_package(self) -> None:
        chapters = chapters_from_timings(CONCRETE_BLOCKS, duration_s=1076.0)
        lines = [f"{format_timestamp(c.start_s)} {c.title}" for c in chapters]
        #  Os cinco capitulos do pacote antigo, na mesma forma.
        for line in lines:
            assert line in FIXTURE
        assert lines[0] == "00:00 An Empire Without a Harbor"

    def test_short_block_joins_the_previous_chapter(self) -> None:
        blocks = [
            {"titulo": "Abertura", "inicio_s": 0.3},
            {"titulo": "Curto demais", "inicio_s": 6.0},
            {"titulo": "Meio", "inicio_s": 40.0},
            {"titulo": "Fim", "inicio_s": 95.0},
        ]
        chapters = chapters_from_timings(blocks, duration_s=100.0)
        #  "Curto demais" comeca 6 s depois da abertura; "Fim" dura so 5 s.
        assert [c.title for c in chapters] == ["Abertura", "Meio"]

    def test_block_without_title_is_ignored(self) -> None:
        blocks = [{"titulo": "", "inicio_s": 0.0}, {"titulo": "Unico", "inicio_s": 20.0}]
        assert chapters_from_timings(blocks, duration_s=60.0) == [Chapter(0, "Unico")]

    @pytest.mark.parametrize(
        ("seconds", "hours", "expected"),
        [
            (0, False, "00:00"),
            (75.9, False, "01:15"),
            (3725, False, "1:02:05"),
            (5, True, "0:00:05"),
        ],
    )
    def test_timestamp(self, seconds: float, hours: bool, expected: str) -> None:
        assert format_timestamp(seconds, with_hours=hours) == expected


DOSSIER = {
    "fontes": [
        {"id": "f1", "titulo": "Roman Aqueducts", "url": "https://c.org/a", "ano": 2018},
        {"id": "f2", "titulo": "Water in the City", "url": "https://j.org/w", "ano": None},
        {"id": "f3", "titulo": "Nunca citada", "url": "https://x.org/n", "ano": 2001},
    ]
}


class TestSources:
    def test_only_what_the_approved_report_cites_in_citation_order(self) -> None:
        report = {
            "itens": [
                {"id": "a1", "fontes": ["f2", "https://c.org/a"]},
                {"id": "a2", "fontes": ["f1", "https://outra.org/fora-do-dossie"]},
            ]
        }
        sources = sources_that_passed(report, DOSSIER)
        assert [s.url for s in sources] == [
            "https://j.org/w",
            "https://c.org/a",
            "https://outra.org/fora-do-dossie",
        ]
        assert sources[1].title == "Roman Aqueducts" and sources[1].year == 2018
        assert sources[2].title is None

    def test_report_without_citations_falls_back_to_the_dossier(self) -> None:
        sources = sources_that_passed({"itens": []}, DOSSIER)
        assert len(sources) == 3

    def test_format(self) -> None:
        full = SourceRef(
            "Roman concrete - Wikipedia", 2024, "https://en.wikipedia.org/wiki/Roman_concrete"
        )
        assert format_source(full) == (
            "- Roman concrete - Wikipedia (2024): https://en.wikipedia.org/wiki/Roman_concrete"
        )
        assert format_source(SourceRef("Sem ano", None, "https://a.b")) == "- Sem ano: https://a.b"
        assert format_source(SourceRef(None, None, "https://a.b")) == "- https://a.b"
        assert format_source(full, bare=True) == "- https://en.wikipedia.org/wiki/Roman_concrete"
        assert format_source(SourceRef("Livro sem link", 1890, None)) == "- Livro sem link (1890)"

    def test_shorten_cuts_between_words(self) -> None:
        title = "Cientistas desvendam segredos de concreto romano que resiste ao mar"
        short = shorten(title, 40)
        assert short == "Cientistas desvendam segredos de..."
        assert len(short) <= 43
        assert shorten("curto", 40) == "curto"


class TestCredits:
    def test_same_line_as_the_old_package(self) -> None:
        credit = credits_from_provenance([PANTHEON])[0]
        line = format_credit(credit, unknown_author="unknown author", public_domain="Public domain")
        assert line in FIXTURE

    def test_unknown_author_and_repeated_photo(self) -> None:
        credits = credits_from_provenance([AMPHORA, None, PANTHEON, AMPHORA])
        assert [c.title for c in credits] == [AMPHORA["titulo"], PANTHEON["titulo"]]
        line = format_credit(
            credits[0], unknown_author="autor desconhecido", public_domain="Domínio público"
        )
        assert line == (
            "- Terracotta amphora (storage jar) MET DP123.jpg — autor desconhecido — CC0 — "
            "https://commons.wikimedia.org/?curid=60407393"
        )

    def test_unverified_link_has_no_license_part(self) -> None:
        pasted = {"titulo": "foto.jpg", "url": "https://site.com/foto.jpg", "verificada": False}
        credit = credits_from_provenance([pasted])[0]
        assert not credit.verified
        assert format_credit(
            credit, unknown_author="autor desconhecido", public_domain="Domínio público"
        ) == ("- foto.jpg — autor desconhecido — https://site.com/foto.jpg")

    def test_public_domain_in_the_channel_language(self) -> None:
        #  O sidecar guarda o rotulo em PT (references/licensing.py); o pacote EN
        #  do Gize saiu com "Domínio público" na descricao em ingles.
        spelterini = {
            "titulo": "Spelterini Pyramids.jpg",
            "autor": "Eduard Spelterini",
            "licenca": "Domínio público",
            "url": "https://commons.wikimedia.org/?curid=3254365",
        }
        credit = credits_from_provenance([spelterini])[0]
        en, pt = texts("en"), texts("pt-br")
        assert " — Public domain — " in format_credit(
            credit, unknown_author=en.unknown_author, public_domain=en.public_domain
        )
        assert " — Domínio público — " in format_credit(
            credit, unknown_author=pt.unknown_author, public_domain=pt.public_domain
        )


class TestChannelTexts:
    def test_pt_disclosure_is_the_approved_text_with_accents(self) -> None:
        assert texts("pt-br").disclosure == (
            "Pesquisa e roteiro produzidos com auxílio de IA, com direção, checagem de fatos "
            "e revisão editorial humanas. Narração e ilustrações geradas por IA. Fontes acima."
        )
        assert texts("pt-br").image_credits == (
            "Ilustrações redesenhadas a partir de fotos de referência:"
        )

    def test_en_texts(self) -> None:
        en = texts("en")
        assert en.sources == "Sources:"
        assert en.disclosure.endswith("Sources above.")
        assert en.image_credits == "Illustrations redrawn from reference photos:"

    def test_missing_text_is_a_config_error(self) -> None:
        with pytest.raises(ConfigError, match="divulgacao"):
            DescriptionTexts.for_channel({"textos": {"fontes": "Fontes:"}})


def _parts(**overrides) -> DescriptionParts:
    base = {
        "paragraphs": ("Primeiro parágrafo.", "Segundo parágrafo."),
        "chapters": tuple(chapters_from_timings(CONCRETE_BLOCKS, 1076.0)),
        "sources": (SourceRef("Roman concrete - Wikipedia", 2024, "https://en.wikipedia.org/x"),),
        "credits": tuple(credits_from_provenance([PANTHEON, AMPHORA])),
        "music": (),
        "discloses": True,
        "duration_s": 1076.0,
    }
    base.update(overrides)
    return DescriptionParts(**base)


class TestDescription:
    def test_sections_in_the_order_of_the_old_package(self) -> None:
        text = render_description(_parts(), texts("en")).text
        order = [
            "Primeiro parágrafo.",
            "00:00 An Empire Without a Harbor",
            "Sources:",
            "Research and script produced with AI assistance",
            "Illustrations redrawn from reference photos:",
            "- Pantheon (Rome), Dome interior.jpg — Wilfredor — CC0",
        ]
        positions = [text.index(piece) for piece in order]
        assert positions == sorted(positions)
        assert "\n\n00:00 An Empire" in text

    def test_no_disclosure_when_the_channel_does_not_ask(self) -> None:
        text = render_description(_parts(discloses=False), texts("pt-br")).text
        assert "Narração e ilustrações" not in text

    def test_music_credits_come_last(self) -> None:
        music = ("- Faixa — Artista — CC BY 4.0",)
        text = render_description(_parts(music=music), texts("pt-br")).text
        assert text.endswith("Música:\n- Faixa — Artista — CC BY 4.0")


class TestDescriptionLimit:
    def test_short_description_is_untouched(self) -> None:
        fitted = fit_description(_parts(), texts("pt-br"))
        assert fitted.layout.title_max is None and not fitted.warnings
        assert fitted.pinned_comment is None

    def test_cascade_until_it_fits_in_5000_bytes(self) -> None:
        long_title = "Um título de fonte acadêmica muito comprido, com subtítulo e tudo mais"
        sources = tuple(
            SourceRef(f"{long_title} {i}", 2020, f"https://revista.org/artigos/{i:03d}")
            for i in range(40)
        )
        credits = tuple(
            Credit(
                f"Foto de referência número {i}.jpg",
                f"Autor {i}",
                "CC BY 4.0",
                f"https://commons.wikimedia.org/?curid={i}",
            )
            for i in range(40)
        )
        music = ("- Faixa — Artista — CC BY 4.0",)
        fitted = fit_description(
            _parts(sources=sources, credits=credits, music=music), texts("pt-br")
        )
        assert byte_length(fitted.text) <= DESCRIPTION_MAX_BYTES
        assert fitted.layout.credits_in_comment
        assert fitted.pinned_comment and "curid=39" in fitted.pinned_comment
        assert "Créditos das ilustrações no comentário fixado." in fitted.text
        #  A atribuicao da musica nunca sai da descricao.
        assert "Música:" in fitted.text
        assert fitted.warnings

    def test_accents_count_as_two_bytes(self) -> None:
        assert byte_length("ação") == 6

    def test_angle_brackets_are_removed(self) -> None:
        fitted = fit_description(_parts(paragraphs=("Use <b>negrito</b>.",)), texts("pt-br"))
        assert "<" not in fitted.text and ">" not in fitted.text


class TestFields:
    def test_title_limits(self) -> None:
        title, warnings = fit_title("Título  com <tag> e espaços")
        assert title == "Título com tag e espaços" and not warnings
        long = " ".join(["palavra"] * 20)
        cut, warnings = fit_title(long)
        assert len(cut) <= 100 and not cut.endswith(" ")
        assert any("cortado" in w for w in warnings)

    def test_tags_count_quotes_commas_and_drop_the_generic_end(self) -> None:
        assert tags_length(["roma", "roma antiga"]) == 4 + 13 + 1
        tags = [f"tag número {i}" for i in range(60)] + ["#história", "Roma", "roma"]
        clean, warnings = fit_tags(tags)
        assert tags_length(clean) <= 500
        assert clean[0] == "tag número 0" and warnings
        clean, _ = fit_tags(["#história", "Roma", "roma", "a,b"])
        assert clean == ["história", "Roma", "a b"]

    def test_unaccented_portuguese(self) -> None:
        assert unaccented_pt("Este video nao conta a historia toda") == [
            "video",
            "nao",
            "historia",
        ]
        assert unaccented_pt("Este vídeo não conta a história toda") == []


class TestThumbnails:
    @pytest.fixture
    def art(self, tmp_path: Path) -> Path:
        path = tmp_path / "arte.png"
        #  Gradiente na proporcao da geracao (1920x1088).
        Image.linear_gradient("L").resize((1920, 1088)).convert("RGB").save(path)
        return path

    def test_base_is_cropped_to_16_by_9(self, art: Path) -> None:
        assert thumbnails.base_image(art).size == (1280, 720)

    @pytest.mark.parametrize("side", ["esquerda", "direita"])
    def test_text_goes_on_the_chosen_side(self, art: Path, side: str) -> None:
        base = thumbnails.base_image(art)
        font = thumbnails.font_file("Comic Relief")
        image = thumbnails.with_text(base, "Sem bombas", side=side, font_path=font)
        diff = ImageChops.difference(image, base).convert("L")
        left = diff.crop((0, 0, 640, 720)).getbbox()
        right = diff.crop((640, 0, 1280, 720)).getbbox()
        text_half, other_half = (left, right) if side == "esquerda" else (right, left)
        assert text_half is not None
        #  Do outro lado so chega a ponta do degrade, nunca o texto.
        assert other_half is None or other_half[2] - other_half[0] < 200

    def test_text_is_upper_case_with_accents_and_never_cut(self) -> None:
        assert thumbnails.thumb_text("o concreto  que não morre") == "O CONCRETO QUE NÃO MORRE"
        assert thumbnails.too_many_words("o concreto que não morre")

    def test_all_line_breaks_are_tried(self) -> None:
        layouts = thumbnails._layouts(["A", "B", "C", "D"])
        assert ["A B C D"] in layouts and ["A", "B", "C D"] in layouts
        assert len(layouts) == 1 + 3 + 3

    def test_jpeg_stays_under_the_limit(self, tmp_path: Path) -> None:
        noise = Image.effect_noise((1280, 720), 60).convert("RGB")
        thumbnails.save_jpeg(noise, tmp_path / "livre.jpg", max_bytes=10**9)
        limit = int((tmp_path / "livre.jpg").stat().st_size * 0.7)
        quality = thumbnails.save_jpeg(noise, tmp_path / "t.jpg", max_bytes=limit)
        assert (tmp_path / "t.jpg").stat().st_size <= limit
        assert quality < 92
