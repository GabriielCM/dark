"""Ingestao de livros e base de conhecimento."""

from __future__ import annotations

import pytest

from mundoantigo.books import KnowledgeBase, chunk_text
from mundoantigo.books.ingest import _as_year, _split_chapters, summarize_rights
from mundoantigo.db.models import Book, RightsStatus


class TestChunking:
    def test_short_text_is_one_chunk(self) -> None:
        assert chunk_text("uma frase curta") == ["uma frase curta"]

    def test_empty_text_yields_nothing(self) -> None:
        assert chunk_text("   ") == []

    def test_long_text_is_split(self) -> None:
        text = "Uma frase de tamanho razoavel sobre aquedutos romanos. " * 120
        chunks = chunk_text(text, size=1200, overlap=150)
        assert len(chunks) > 1
        assert all(len(c) <= 1400 for c in chunks)

    def test_chunks_cover_the_whole_text(self) -> None:
        text = "".join(f"Sentenca numero {i}. " for i in range(400))
        joined = " ".join(chunk_text(text))
        assert "Sentenca numero 0." in joined
        assert "Sentenca numero 399." in joined

    def test_prefers_sentence_boundaries(self) -> None:
        text = ("Primeira parte do texto. " * 60) + ("Segunda parte do texto. " * 60)
        chunks = chunk_text(text, size=800, overlap=50)
        #  Nenhum trecho termina no meio de uma palavra.
        assert all(not c.endswith(("part", "text", "Segund")) for c in chunks)


class TestChapterDetection:
    def test_detects_numbered_chapters(self) -> None:
        text = "\n".join(
            ["Prefacio " * 100]
            + [f"Capitulo {n}\n" + f"Conteudo do capitulo {n}. " * 30 for n in range(1, 4)]
        )
        chapters = _split_chapters(text, [])
        assert len(chapters) >= 3
        assert any("Conteudo do capitulo 2" in body for _, body in chapters)

    def test_text_without_chapters_stays_whole(self) -> None:
        chapters = _split_chapters("Um texto corrido sem divisao nenhuma.", [])
        assert len(chapters) == 1
        assert chapters[0][0] is None

    def test_recognizes_english_headings(self) -> None:
        text = "\n".join(f"Chapter {n}\n" + "Body text. " * 40 for n in range(1, 4))
        assert len(_split_chapters(text, [])) >= 3


class TestYearParsing:
    """Um ano chutado corrompe a classificacao de direitos."""

    @pytest.mark.parametrize(
        ("entrada", "esperado"),
        [
            (1890, 1890),
            ("1890", 1890),
            ("c. 1890", None),
            (None, None),
            ("", None),
            ("desconhecido", None),
            (3000, None),
            (True, None),
        ],
    )
    def test_implausible_values_become_none(self, entrada, esperado) -> None:
        assert _as_year(entrada) == esperado

    def test_negative_years_are_accepted(self) -> None:
        """Autores da Antiguidade tem ano de morte negativo."""
        assert _as_year(-400) == -400


class TestKnowledgeBase:
    def test_search_finds_relevant_chunk(self, sessions) -> None:
        with sessions() as s:
            s.add(
                Book(
                    id="b1",
                    filename="x.pdf",
                    format="pdf",
                    sha256="a" * 64,
                    title="Aquedutos",
                    rights_status=RightsStatus.LIVRE,
                )
            )
            s.commit()

        kb = KnowledgeBase(sessions)
        kb.index_book(
            "b1",
            [
                (
                    1,
                    "Os aquedutos romanos moviam agua por gravidade ao longo de "
                    "dezenas de quilometros.",
                ),
                (2, "A metalurgia do bronze exigia estanho, um metal raro no Mediterraneo antigo."),
            ],
        )

        results = kb.search("aquedutos gravidade agua", limit=2)
        assert results
        assert "aquedutos" in results[0].text.lower()

    def test_rights_note_travels_with_the_excerpt(self, sessions) -> None:
        """O modelo nunca recebe trecho de obra protegida sem o aviso junto."""
        with sessions() as s:
            s.add(
                Book(
                    id="livre",
                    filename="a.pdf",
                    format="pdf",
                    sha256="a" * 64,
                    rights_status=RightsStatus.LIVRE,
                )
            )
            s.add(
                Book(
                    id="protegido",
                    filename="b.pdf",
                    format="pdf",
                    sha256="b" * 64,
                    rights_status=RightsStatus.FONTE_APENAS,
                )
            )
            s.commit()

        kb = KnowledgeBase(sessions)
        kb.index_book("livre", [(1, "Texto sobre aquedutos e engenharia romana antiga.")])
        kb.index_book("protegido", [(1, "Texto sobre aquedutos e engenharia romana antiga.")])

        notas = {r.book_id: r.rights_note for r in kb.search("aquedutos engenharia", limit=5)}
        assert "pode ser adaptado" in notas["livre"]
        assert "nao reproduza" in notas["protegido"]

    def test_reindexing_replaces_old_chunks(self, sessions) -> None:
        with sessions() as s:
            s.add(Book(id="b1", filename="x.pdf", format="pdf", sha256="a" * 64))
            s.commit()
        kb = KnowledgeBase(sessions)
        kb.index_book("b1", [(1, "Primeira versao do texto sobre Roma antiga.")])
        kb.index_book("b1", [(1, "Segunda versao do texto sobre Roma antiga.")])
        results = kb.search("Roma antiga versao", limit=10)
        assert len(results) == 1
        assert "Segunda" in results[0].text

    def test_search_on_empty_base_returns_nothing(self, sessions) -> None:
        assert KnowledgeBase(sessions).search("qualquer coisa") == []

    def test_chapter_topics_carry_the_rights_policy(self, sessions) -> None:
        with sessions() as s:
            s.add(
                Book(
                    id="b1",
                    filename="x.pdf",
                    format="pdf",
                    sha256="a" * 64,
                    title="Roma",
                    rights_status=RightsStatus.FONTE_APENAS,
                    chapters=[{"numero": 1, "titulo": "A fundacao"}],
                )
            )
            s.commit()
        topics = KnowledgeBase(sessions).chapter_topics("b1")
        assert len(topics) == 1
        assert topics[0]["pode_adaptar"] is False
        assert "fonte de fatos" in topics[0]["observacao"]

    def test_chapter_topics_of_unknown_book(self, sessions) -> None:
        assert KnowledgeBase(sessions).chapter_topics("nao-existe") == []


def test_summarize_rights_for_panel(sessions) -> None:
    book = Book(
        id="b1",
        filename="x.pdf",
        format="pdf",
        sha256="a" * 64,
        rights_status=RightsStatus.LIVRE,
        rights_reason="dominio publico",
    )
    resumo = summarize_rights(book)
    assert resumo["livre"] is True
    assert resumo["pode_adaptar"] is True
    assert resumo["motivo"] == "dominio publico"
