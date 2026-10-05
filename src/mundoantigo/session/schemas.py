"""Formato dos arquivos que a sessao entrega ao pipeline.

Sao os mesmos formatos que as etapas 2 e 3 produziam pelo OpenRouter, com o
que faltava ficando explicito: IDs nas afirmacoes do dossie e nas fontes, o
titulo de cada bloco (vira titulo de capitulo na tela e na descricao), os
comentarios do MC (baloes, nao narrados) e as tarjas de local e epoca.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    #  Campo desconhecido e quase sempre erro de digitacao: melhor recusar.
    model_config = ConfigDict(extra="forbid")


class Fonte(_Strict):
    id: str
    #  Veiculo e titulo como publicados, no idioma da fonte ("Wikipedia, Khufu"):
    #  o mesmo titulo vai para as descricoes PT e EN. O ano vai em `ano`.
    titulo: str | None = None
    url: str | None = None
    tipo: Literal[
        "academica", "institucional", "jornalistica", "livro", "enciclopedia", "outra"
    ] = "outra"
    ano: int | None = None


class AfirmacaoDossie(_Strict):
    id: str
    texto: str
    fontes: list[str] = Field(description="ids de `fontes`")
    tipo: Literal["consenso", "disputa", "especulacao"] = "consenso"


class BlocoDossie(_Strict):
    titulo: str
    conteudo: str = ""
    afirmacoes: list[AfirmacaoDossie] = Field(default_factory=list)


class Dossie(_Strict):
    tema: str
    resumo: str
    angulo: str = ""
    blocos: list[BlocoDossie]
    lacunas: list[str] = Field(default_factory=list)
    fontes: list[Fonte]


class BlocoRoteiro(_Strict):
    secao: Literal["gancho", "contexto", "desenvolvimento", "revelacao", "fechamento"]
    #  Titulo do capitulo: aparece no video e na descricao, sempre igual.
    titulo: str
    narracao: str
    afirmacoes_usadas: list[str] = Field(default_factory=list, description="ids do dossie")
    #  Baloes do MC: 3 a 8 palavras, secos e ironicos, nunca narrados.
    comentarios_mc: list[str] = Field(default_factory=list)
    #  Tarjas de local e epoca, em caixa alta: "ACAMPAMENTO ROMANO, SÉCULO I".
    tarjas: list[str] = Field(default_factory=list)


class Roteiro(_Strict):
    titulo_provisorio: str
    gancho: str
    #  Figurino do MC neste video, em ingles (vai para o prompt de imagem).
    figurino: str | None = None
    #  Epoca e lugar do video, em ingles, com o que as pessoas vestem e do que
    #  as construcoes sao feitas. Entra no prompt de toda imagem: sem isso,
    #  "workers" e "city" sairam europeus e modernos no video do Egito (04/10).
    ambientacao: str | None = None
    blocos: list[BlocoRoteiro]
    pedidos_de_pesquisa: list[str] = Field(default_factory=list)
    palavras_total: int | None = None


class ItemFato(_Strict):
    id: str
    afirmacao: str
    bloco: int
    fontes: list[str]
    confianca: Literal["alta", "media", "baixa"]
    justificativa: str
    correcao_sugerida: str | None = None


class RelatorioFatos(_Strict):
    itens: list[ItemFato]
