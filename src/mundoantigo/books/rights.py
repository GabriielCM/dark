"""Classificacao de direitos autorais (brief 4.2).

Regras implementadas:

- **Brasil:** dominio publico 70 anos apos a morte do autor. A protecao cai em
  1o de janeiro do ano seguinte ao 70o aniversario da morte (LDA 9.610/98,
  art. 41), entao a comparacao e estrita.
- **EUA:** obras publicadas ha 95 anos ou mais estao em dominio publico. Em
  2026, isso cobre o que foi publicado ate 1930. A janela e rolante, calculada
  a partir do ano corrente, e nao um numero fixo no codigo.
- **Traducao e obra separada:** se ha tradutor, ele precisa satisfazer as
  mesmas regras. Uma obra de Tucidides e livre; a traducao de 1998 dela, nao.

Postura: **na duvida, protegida.** Dado ausente nunca vira presuncao de
liberdade. O custo de errar para o lado permissivo e uma reivindicacao de
direitos autorais num canal que depende de monetizacao; o custo de errar para o
lado restritivo e usar o livro apenas como fonte de fatos, que ja e util.

Isto e uma regra operacional conservadora, nao parecer juridico.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from ..db.models import RightsStatus

#  Brasil: LDA 9.610/98, art. 41.
BR_YEARS_AFTER_DEATH = 70
#  EUA: 95 anos a partir da publicacao, para obras publicadas antes de 1978.
US_YEARS_AFTER_PUBLICATION = 95


def current_year() -> int:
    return datetime.now(UTC).year


@dataclass(frozen=True, slots=True)
class JurisdictionVerdict:
    jurisdiction: str
    free: bool
    reason: str
    #  Ano em que a obra entra (ou entrou) em dominio publico, quando calculavel.
    free_from: int | None = None


@dataclass(frozen=True, slots=True)
class RightsVerdict:
    status: RightsStatus
    reason: str
    jurisdictions: tuple[JurisdictionVerdict, ...] = ()
    missing_data: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def can_be_adapted(self) -> bool:
        """Adaptar ou narrar exige obra livre (brief 4.2)."""
        return self.status is RightsStatus.LIVRE

    @property
    def can_be_used_as_source(self) -> bool:
        """Toda obra pode ser fonte de fatos; o roteiro e original."""
        return True

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "motivo": self.reason,
            "jurisdicoes": [
                {
                    "jurisdicao": j.jurisdiction,
                    "livre": j.free,
                    "motivo": j.reason,
                    "livre_desde": j.free_from,
                }
                for j in self.jurisdictions
            ],
            "dados_ausentes": list(self.missing_data),
            **self.detail,
        }


@dataclass(frozen=True, slots=True)
class WorkFacts:
    """O que se sabe sobre a obra. `None` significa desconhecido, nunca zero."""

    title: str | None = None
    author: str | None = None
    author_death_year: int | None = None
    translator: str | None = None
    translator_death_year: int | None = None
    original_year: int | None = None
    edition_year: int | None = None


def _brazil(death_year: int | None, *, who: str, year: int) -> JurisdictionVerdict:
    if death_year is None:
        return JurisdictionVerdict(
            "BR", False, f"ano de morte {who} desconhecido — sem isso nao ha como contar 70 anos"
        )
    free_from = death_year + BR_YEARS_AFTER_DEATH + 1
    if year >= free_from:
        return JurisdictionVerdict(
            "BR",
            True,
            f"{who} morreu em {death_year}; dominio publico desde {free_from}",
            free_from,
        )
    return JurisdictionVerdict(
        "BR",
        False,
        f"{who} morreu em {death_year}; protegida ate {free_from - 1}",
        free_from,
    )


def _usa(publication_year: int | None, *, year: int) -> JurisdictionVerdict:
    if publication_year is None:
        return JurisdictionVerdict(
            "US", False, "ano de publicacao desconhecido — sem isso nao ha como contar 95 anos"
        )
    cutoff = year - US_YEARS_AFTER_PUBLICATION
    if publication_year <= cutoff:
        return JurisdictionVerdict(
            "US",
            True,
            f"publicada em {publication_year}, ate {cutoff} esta em dominio publico",
            publication_year + US_YEARS_AFTER_PUBLICATION,
        )
    return JurisdictionVerdict(
        "US",
        False,
        f"publicada em {publication_year}; em {year} o corte e {cutoff}",
        publication_year + US_YEARS_AFTER_PUBLICATION,
    )


def classify(facts: WorkFacts, *, year: int | None = None) -> RightsVerdict:
    """Classifica uma obra. Toda decisao vem com justificativa registrada."""
    ref_year = year or current_year()
    missing: list[str] = []
    verdicts: list[JurisdictionVerdict] = []

    if facts.author_death_year is None:
        missing.append("ano_morte_autor")
    if facts.original_year is None:
        missing.append("ano_publicacao_original")

    #  Obra em si.
    br_author = _brazil(facts.author_death_year, who="o autor", year=ref_year)
    us_work = _usa(facts.original_year, year=ref_year)
    verdicts += [br_author, us_work]

    #  Traducao, quando existe, e obra separada com prazo proprio.
    translation_free = True
    if facts.translator:
        if facts.translator_death_year is None:
            missing.append("ano_morte_tradutor")
        #  A traducao "publica-se" na edicao, nao no original.
        br_translator = _brazil(facts.translator_death_year, who="o tradutor", year=ref_year)
        us_translation = _usa(facts.edition_year or facts.original_year, year=ref_year)
        verdicts += [
            JurisdictionVerdict(
                "BR (traducao)", br_translator.free, br_translator.reason, br_translator.free_from
            ),
            JurisdictionVerdict(
                "US (traducao)",
                us_translation.free,
                us_translation.reason,
                us_translation.free_from,
            ),
        ]
        translation_free = br_translator.free and us_translation.free
        if facts.edition_year is None and facts.original_year is None:
            missing.append("ano_edicao")

    work_free = br_author.free and us_work.free

    if work_free and translation_free:
        return RightsVerdict(
            status=RightsStatus.LIVRE,
            reason=(
                "dominio publico no Brasil e nos EUA"
                + (", incluindo a traducao" if facts.translator else "")
                + ". Pode ser adaptada ou narrada, sempre com contexto e comentario."
            ),
            jurisdictions=tuple(verdicts),
            missing_data=tuple(dict.fromkeys(missing)),
            detail={"ano_referencia": ref_year},
        )

    blockers = [v.reason for v in verdicts if not v.free]
    if missing:
        reason = (
            "status incerto: faltam dados ("
            + ", ".join(dict.fromkeys(missing))
            + "). Na duvida, entra apenas como fonte de fatos."
        )
    elif facts.translator and work_free and not translation_free:
        reason = (
            "a obra original esta em dominio publico, mas a traducao nao. "
            "A traducao e obra separada — entra apenas como fonte de fatos."
        )
    else:
        reason = "obra protegida: " + "; ".join(blockers[:2])

    return RightsVerdict(
        status=RightsStatus.FONTE_APENAS,
        reason=reason,
        jurisdictions=tuple(verdicts),
        missing_data=tuple(dict.fromkeys(missing)),
        detail={"ano_referencia": ref_year},
    )


def usage_policy(status: RightsStatus) -> dict[str, Any]:
    """O que o pipeline pode fazer com a obra. Consultado pela etapa de pesquisa."""
    if status is RightsStatus.LIVRE:
        return {
            "adaptar": True,
            "narrar": True,
            "serie_por_capitulos": True,
            "citacao": "livre, com contexto e comentario",
            #  Narracao literal sem comentario cai na politica de conteudo
            #  inautentico do YouTube (brief 4.2).
            "observacao": "narracao literal sem comentario e proibida pela politica do canal",
        }
    return {
        "adaptar": False,
        "narrar": False,
        "serie_por_capitulos": False,
        "citacao": "apenas trechos curtos, creditados",
        "observacao": (
            "entra so como fonte de fatos: o roteiro e original e os capitulos servem "
            "apenas como guia de pauta"
        ),
    }
