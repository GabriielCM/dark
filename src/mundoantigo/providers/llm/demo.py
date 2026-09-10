"""Respostas de ensaio.

O modo `--ensaio` existe para percorrer o pipeline inteiro sem gastar: antes de
ligar um provedor pago, da para ver onde cada artefato cai, conferir o painel e
medir quanto tempo a montagem leva.

Para isso servir de alguma coisa, as respostas precisam ser coerentes entre si
— um relatorio de fatos vazio faria o gate bloquear no ensaio, o que testa o
gate mas nao testa o resto.
"""

from __future__ import annotations

import json
from typing import Any

#  Marcadores dos prompts do projeto. Se um prompt mudar de abertura, o ensaio
#  cai no JSON generico e a etapa correspondente falha de forma visivel — o que
#  e melhor que passar despercebido.
_MARKERS = {
    "dossie": "Monte um dossiê",
    "checagem": "verificador de fatos",
    "roteiro": "roteiros de documentário",
    "reescrita": "relatório de fatos reprovou",
    "adaptacao": "Adapt this Brazilian",
    "storyboard": "Quebre o roteiro",
    "metadados": "metadados de publicação",
    "livro": "dados bibliográficos",
}

_FONTES = [
    {
        "id": "f1",
        "titulo": "Fonte de ensaio A",
        "url": "https://exemplo.edu/a",
        "tipo": "academica",
        "ano": 2019,
    },
    {
        "id": "f2",
        "titulo": "Fonte de ensaio B",
        "url": "https://exemplo.edu/b",
        "tipo": "institucional",
        "ano": 2021,
    },
]

#  ~12 minutos a 150 palavras por minuto. O ensaio produz um video de tamanho
#  realista para que a montagem e o custo tenham ordem de grandeza util.
_PARAGRAFO_PT = (
    "Este e um texto de ensaio, gerado sem chamar nenhum provedor externo. "
    "Ele existe para exercitar a narracao, o alinhamento e a montagem com um "
    "volume de palavras parecido com o de um roteiro de verdade. "
)
_PARAGRAFO_EN = (
    "This is rehearsal text, produced without calling any external provider. "
    "It exists to exercise narration, alignment and assembly with a word count "
    "close to that of a real script. "
)

_BLOCOS = ("gancho", "contexto", "desenvolvimento", "revelacao", "fechamento")


def _roteiro(paragrafo: str, titulo: str) -> dict[str, Any]:
    narracao = (paragrafo * 12).strip()
    blocos: list[dict[str, Any]] = [
        {
            "secao": secao,
            "titulo": f"{secao.title()} de ensaio",
            "narracao": narracao,
            "afirmacoes_usadas": [f"a{i + 1}"],
        }
        for i, secao in enumerate(_BLOCOS)
    ]
    return {
        "titulo_provisorio": titulo,
        "gancho": paragrafo[:90],
        "blocos": blocos,
        "pedidos_de_pesquisa": [],
        "palavras_total": len(narracao.split()) * len(blocos),
        "_ensaio": True,
    }


def _cenas(quantidade: int = 80) -> dict[str, Any]:
    camaras = ("zoom_in", "pan_left", "estatica", "zoom_out", "pan_right")
    return {
        "cenas": [
            {
                "indice": i,
                "narracao": f"trecho de ensaio {i}",
                "duracao_estimada_s": 9.0,
                "prompt_cenario": f"rehearsal scene {i}, wide establishing view",
                "camadas": {
                    "frente": "foreground detail",
                    "meio": "midground subject",
                    "fundo": "distant horizon",
                },
                "camera": camaras[i % len(camaras)],
                "personagem": {"pose": "explicando", "posicao": "direita"} if i % 4 == 0 else None,
                "sfx": None,
                "musica": "descoberta" if i % 10 == 0 else None,
            }
            for i in range(1, quantidade + 1)
        ]
    }


def demo_responder() -> Any:
    """Devolve uma funcao prompt -> resposta JSON, coerente entre as etapas."""

    def responde(prompt: str) -> str:
        def tem(chave: str) -> bool:
            return _MARKERS[chave] in prompt

        if tem("dossie"):
            return json.dumps(
                {
                    "tema": "ensaio",
                    "resumo": "Dossie de ensaio, sem pesquisa real.",
                    "angulo": "exercitar o pipeline",
                    "blocos": [
                        {
                            "titulo": f"Bloco {i + 1}",
                            "conteudo": "Conteudo de ensaio.",
                            "afirmacoes": [
                                {
                                    "texto": f"Afirmacao de ensaio {i + 1}.",
                                    "fontes": ["f1", "f2"],
                                    "tipo": "consenso",
                                }
                            ],
                        }
                        for i in range(len(_BLOCOS))
                    ],
                    "lacunas": [],
                    "fontes": _FONTES,
                },
                ensure_ascii=False,
            )

        if tem("checagem"):
            #  Todas com duas fontes: o gate aprova e o ensaio segue adiante.
            return json.dumps(
                {
                    "itens": [
                        {
                            "id": f"a{i + 1}",
                            "afirmacao": f"Afirmacao de ensaio {i + 1}.",
                            "bloco": i,
                            "fontes": ["https://exemplo.edu/a", "https://exemplo.edu/b"],
                            "confianca": "alta",
                            "justificativa": "duas fontes de ensaio",
                            "correcao_sugerida": None,
                        }
                        for i in range(len(_BLOCOS))
                    ]
                },
                ensure_ascii=False,
            )

        if tem("reescrita"):
            return json.dumps({"correcoes": []}, ensure_ascii=False)

        if tem("roteiro"):
            return json.dumps(_roteiro(_PARAGRAFO_PT, "Video de ensaio"), ensure_ascii=False)

        if tem("adaptacao"):
            return json.dumps(_roteiro(_PARAGRAFO_EN, "Rehearsal video"), ensure_ascii=False)

        if tem("storyboard"):
            return json.dumps(_cenas(), ensure_ascii=False)

        if tem("metadados"):
            return json.dumps(
                {
                    "titulo": "Video de ensaio",
                    "titulos_alternativos": ["Ensaio do pipeline"],
                    "descricao": "Descricao de ensaio, gerada sem provedor externo.",
                    "tags": ["ensaio", "pipeline", "teste"],
                    "capitulos": [
                        {"tempo": "00:00", "titulo": "Abertura"},
                        {"tempo": "04:00", "titulo": "Meio"},
                        {"tempo": "09:00", "titulo": "Fechamento"},
                    ],
                    "thumbnail": {
                        "conceito": "composicao de ensaio",
                        "prompt": "rehearsal thumbnail, single bold subject",
                        "texto": "ENSAIO",
                        "versao_sem_texto": True,
                    },
                },
                ensure_ascii=False,
            )

        if tem("livro"):
            return json.dumps(
                {
                    "titulo": "Livro de ensaio",
                    "subtitulo": None,
                    "autor": "Autor de Ensaio",
                    "autor_ano_morte": None,
                    "tradutor": None,
                    "tradutor_ano_morte": None,
                    "idioma": "pt",
                    "ano_publicacao_original": None,
                    "ano_desta_edicao": None,
                    "editora": None,
                    "capitulos": [],
                    "confianca": "baixa",
                    "observacoes": "metadados de ensaio: nada foi identificado de verdade",
                },
                ensure_ascii=False,
            )

        return json.dumps({"ensaio": True}, ensure_ascii=False)

    return responde
