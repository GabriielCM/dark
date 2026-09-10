"""Classificacao de direitos autorais (brief 4.2).

A decisao mais cara do sistema: um falso "livre" vira reivindicacao de direitos
num canal que depende de monetizacao. Estes testes fixam a postura conservadora
— na duvida, protegida.
"""

from __future__ import annotations

from mundoantigo.books.rights import WorkFacts, classify, usage_policy
from mundoantigo.db.models import RightsStatus

ANO = 2026  # ano de referencia fixo: o teste nao pode mudar de resultado em janeiro


class TestObraLivre:
    def test_autor_e_publicacao_antigos(self) -> None:
        """Gibbon: morreu em 1794, publicou em 1776. Livre nas duas jurisdicoes."""
        verdict = classify(
            WorkFacts(author="Edward Gibbon", author_death_year=1794, original_year=1776),
            year=ANO,
        )
        assert verdict.status is RightsStatus.LIVRE
        assert verdict.can_be_adapted

    def test_limite_brasileiro_exato(self) -> None:
        """70 anos apos a morte: a protecao cai em 1o de janeiro do ano seguinte."""
        no_limite = classify(
            WorkFacts(author="X", author_death_year=1955, original_year=1900), year=ANO
        )
        assert no_limite.status is RightsStatus.LIVRE  # 1955 + 70 + 1 = 2026

        ainda_protegida = classify(
            WorkFacts(author="X", author_death_year=1956, original_year=1900), year=ANO
        )
        assert ainda_protegida.status is RightsStatus.FONTE_APENAS

    def test_limite_americano_e_rolante(self) -> None:
        """95 anos apos a publicacao. Em 2026, o corte e 1931."""
        livre = classify(
            WorkFacts(author="X", author_death_year=1900, original_year=1931), year=ANO
        )
        assert livre.status is RightsStatus.LIVRE

        protegida = classify(
            WorkFacts(author="X", author_death_year=1900, original_year=1932), year=ANO
        )
        assert protegida.status is RightsStatus.FONTE_APENAS

    def test_janela_americana_anda_com_o_ano(self) -> None:
        facts = WorkFacts(author="X", author_death_year=1900, original_year=1932)
        assert classify(facts, year=2026).status is RightsStatus.FONTE_APENAS
        assert classify(facts, year=2027).status is RightsStatus.LIVRE


class TestTraducao:
    """A traducao e obra separada. E o erro mais facil de cometer aqui."""

    def test_original_livre_traducao_moderna_bloqueia(self) -> None:
        verdict = classify(
            WorkFacts(
                author="Tucidides",
                author_death_year=-400,
                original_year=-431,
                translator="Tradutor Vivo",
                translator_death_year=None,
                edition_year=1998,
            ),
            year=ANO,
        )
        assert verdict.status is RightsStatus.FONTE_APENAS
        assert not verdict.can_be_adapted
        assert "ano_morte_tradutor" in verdict.missing_data

    def test_traducao_antiga_com_tradutor_morto_ha_muito(self) -> None:
        verdict = classify(
            WorkFacts(
                author="Homero",
                author_death_year=-700,
                original_year=-750,
                translator="Odorico Mendes",
                translator_death_year=1864,
                edition_year=1874,
            ),
            year=ANO,
        )
        assert verdict.status is RightsStatus.LIVRE
        assert "incluindo a traducao" in verdict.reason

    def test_tradutor_morto_recentemente_bloqueia(self) -> None:
        verdict = classify(
            WorkFacts(
                author="Homero",
                author_death_year=-700,
                original_year=-750,
                translator="Tradutor",
                translator_death_year=1990,
                edition_year=1960,
            ),
            year=ANO,
        )
        assert verdict.status is RightsStatus.FONTE_APENAS
        assert "traducao" in verdict.reason.lower()

    def test_jurisdicoes_da_traducao_aparecem_na_justificativa(self) -> None:
        verdict = classify(
            WorkFacts(
                author="X",
                author_death_year=1800,
                original_year=1820,
                translator="T",
                translator_death_year=1990,
                edition_year=1970,
            ),
            year=ANO,
        )
        rotulos = {j.jurisdiction for j in verdict.jurisdictions}
        assert rotulos == {"BR", "US", "BR (traducao)", "US (traducao)"}


class TestDadosAusentes:
    """Na duvida, protegida. Dado ausente nunca vira presuncao de liberdade."""

    def test_sem_ano_de_morte_do_autor(self) -> None:
        verdict = classify(WorkFacts(author="Anonimo", original_year=1850), year=ANO)
        assert verdict.status is RightsStatus.FONTE_APENAS
        assert "ano_morte_autor" in verdict.missing_data
        assert "incerto" in verdict.reason

    def test_sem_ano_de_publicacao(self) -> None:
        verdict = classify(WorkFacts(author="X", author_death_year=1800), year=ANO)
        assert verdict.status is RightsStatus.FONTE_APENAS
        assert "ano_publicacao_original" in verdict.missing_data

    def test_obra_sem_nenhum_dado(self) -> None:
        verdict = classify(WorkFacts(), year=ANO)
        assert verdict.status is RightsStatus.FONTE_APENAS
        assert len(verdict.missing_data) >= 2


class TestPolitica:
    def test_obra_livre_pode_ser_adaptada(self) -> None:
        policy = usage_policy(RightsStatus.LIVRE)
        assert policy["adaptar"] and policy["narrar"] and policy["serie_por_capitulos"]
        #  Narracao literal sem comentario cai na politica de conteudo inautentico.
        assert "literal" in policy["observacao"]

    def test_obra_protegida_so_como_fonte(self) -> None:
        policy = usage_policy(RightsStatus.FONTE_APENAS)
        assert not policy["adaptar"]
        assert not policy["narrar"]
        assert not policy["serie_por_capitulos"]
        assert "fonte de fatos" in policy["observacao"]

    def test_nao_classificada_e_tratada_como_protegida(self) -> None:
        policy = usage_policy(RightsStatus.NAO_CLASSIFICADA)
        assert not policy["adaptar"]

    def test_qualquer_obra_serve_como_fonte(self) -> None:
        """O roteiro e original; a obra aparece nas fontes da descricao."""
        verdict = classify(WorkFacts(author="X"), year=ANO)
        assert verdict.can_be_used_as_source


def test_justificativa_e_registrada_sempre() -> None:
    """A classificacao fica registrada com justificativa (brief 4.2)."""
    for facts in (
        WorkFacts(author="X", author_death_year=1794, original_year=1776),
        WorkFacts(author="Y", author_death_year=2000, original_year=1990),
        WorkFacts(),
    ):
        verdict = classify(facts, year=ANO)
        payload = verdict.as_dict()
        assert payload["motivo"]
        assert payload["jurisdicoes"]
        assert all(j["motivo"] for j in payload["jurisdicoes"])
