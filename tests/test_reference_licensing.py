"""Licenca das fotos do Commons (fase B4), incluindo os creditos problematicos
do pacote antigo (tests/fixtures/pacote_exemplo.txt)."""

from __future__ import annotations

from typing import Any

import pytest

from mundoantigo.references.licensing import classify, clean_author


def meta(**fields: str) -> dict[str, Any]:
    """extmetadata no formato da API: cada campo e {"value": ...}."""
    return {k: {"value": v, "source": "commons-desc-page"} for k, v in fields.items()}


class TestAccepted:
    def test_cc_by_keeps_author_and_requires_credit(self) -> None:
        verdict = classify(
            meta(
                LicenseShortName="CC BY 2.0",
                License="cc-by-2.0",
                Artist='<a href="//commons.wikimedia.org/wiki/User:X">James St. John</a>',
                AttributionRequired="true",
            )
        )
        assert verdict.accepted
        assert verdict.license == "CC BY 2.0"
        assert verdict.author == "James St. John"
        assert verdict.attribution_required

    def test_cc0_without_author_is_accepted(self) -> None:
        #  "Terracotta amphora (storage jar) MET... — autor nao informado — CC0"
        verdict = classify(meta(LicenseShortName="CC0", License="cc0", Artist=""))
        assert verdict.accepted
        assert verdict.author is None
        assert not verdict.attribution_required

    def test_cc0_marked_copyrighted_is_not_a_contradiction(self) -> None:
        #  "Pantheon (Rome), Dome interior.jpg — Wilfredor — CC0", do pacote antigo:
        #  o Commons marca CC0 como `Copyrighted`, porque e renuncia a um direito.
        verdict = classify(
            meta(
                LicenseShortName="CC0",
                License="cc0",
                UsageTerms="Creative Commons Zero, Public Domain Dedication",
                Copyrighted="True",
                Artist="Wilfredor",
            )
        )
        assert verdict.accepted
        assert verdict.license == "CC0"

    def test_public_domain_with_a_wiki_signature(self) -> None:
        #  "Goat fur skin.jpg — Kürschner (talk) 07:53, 24 March 2012 (UTC)"
        verdict = classify(
            meta(
                LicenseShortName="Public domain",
                License="pd",
                Artist="Kürschner (talk) 07:53, 24 March 2012 (UTC)",
                Copyrighted="False",
            )
        )
        assert verdict.accepted
        assert verdict.license == "Domínio público"
        assert verdict.author == "Kürschner"


class TestRejected:
    def test_all_rights_reserved_next_to_cc_by(self) -> None:
        #  "Roman chain links — All rights reserved, Philippa Walton — CC BY 2.0"
        verdict = classify(
            meta(
                LicenseShortName="CC BY 2.0",
                License="cc-by-2.0",
                Artist="All rights reserved, Philippa Walton, 2018-03-01 09:54:08",
            )
        )
        assert not verdict.accepted
        assert "contradicao" in verdict.reason

    @pytest.mark.parametrize(
        ("short", "code", "expected"),
        [
            ("CC BY-SA 4.0", "cc-by-sa-4.0", "SA"),
            ("CC BY-NC 2.0", "cc-by-nc-2.0", "NC"),
            ("CC BY-ND 3.0", "cc-by-nd-3.0", "ND"),
            ("GFDL", "gfdl", "GFDL"),
        ],
    )
    def test_share_alike_non_commercial_and_no_derivatives(self, short, code, expected) -> None:
        verdict = classify(meta(LicenseShortName=short, License=code, Artist="Autor"))
        assert not verdict.accepted
        assert expected in verdict.reason

    def test_share_alike_hidden_in_the_usage_terms(self) -> None:
        verdict = classify(
            meta(
                LicenseShortName="CC BY 3.0",
                UsageTerms="Creative Commons Attribution-Share Alike 3.0",
                Artist="Autor",
            )
        )
        assert not verdict.accepted

    def test_public_domain_marked_copyrighted_is_a_contradiction(self) -> None:
        verdict = classify(meta(LicenseShortName="Public domain", License="pd", Copyrighted="True"))
        assert not verdict.accepted

    def test_non_free_and_restricted_files(self) -> None:
        assert not classify(meta(LicenseShortName="CC0", NonFree="true")).accepted
        assert not classify(meta(LicenseShortName="CC0", Restrictions="trademarked")).accepted

    def test_cc_by_without_author_cannot_be_credited(self) -> None:
        verdict = classify(meta(LicenseShortName="CC BY 4.0", License="cc-by-4.0", Artist=""))
        assert not verdict.accepted
        assert "autor" in verdict.reason

    def test_unknown_license(self) -> None:
        assert not classify(meta(LicenseShortName="Copyrighted free use?")).accepted


def test_clean_author_drops_html_and_unknown() -> None:
    assert clean_author("<span>Jebulon</span>") == "Jebulon"
    assert clean_author("Unknown author") is None
    assert clean_author("Creator:Princeton Group") == "Princeton Group"
    assert clean_author("") is None
