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
import re
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
    "encurtar": "narration are too long",
    "storyboard": "Quebre o roteiro",
    "thumbnail": "Proponha a thumbnail",
    "metadados": "metadados de publicação",
    "cortes": "Escolha os cortes deste vídeo",
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


_TIPOS = ("atuada", "lugar", "plano_detalhe", "cartao", "metafora", "plano_geral")
_CAMERAS = ("zoom_in", "pan_left", "estatica", "zoom_out", "pan_right")


def _storyboard_v2(prompt: str) -> dict[str, Any]:
    """Direcao das cenas de um bloco: le os indices que vieram no prompt."""
    indices = [int(n) for n in re.findall(r'"indice": (\d+)', prompt)]
    cenas = []
    for posicao, i in enumerate(indices):
        tipo = _TIPOS[i % len(_TIPOS)]
        cena: dict[str, Any] = {
            "indice": i,
            "tipo": tipo,
            "descricao_visual": f"rehearsal scene {i}, a Roman aqueduct crossing a dry valley",
            "camera": _CAMERAS[i % len(_CAMERAS)],
            "tarja": 0 if posicao == 0 else None,
            "balao": 0 if posicao == 1 else None,
        }
        if tipo == "atuada":
            cena["personagem"] = {"acao": "pointing at the arches", "expressao": "curious"}
        if tipo == "cartao":
            cena["cartao"] = {
                "pecas": [
                    {
                        "descricao": "a Roman groma surveying tool",
                        "rotulo": {"pt": "groma", "en": "groma"},
                    },
                ],
                "comparacao": False,
            }
            cena["mc"] = {"pose": "apontando", "lado": "direita"}
        if tipo == "lugar":
            cena["referencia"] = {"busca": "Pont du Gard aqueduct", "alvo": "aqueduct arches"}
        cenas.append(cena)
    return {"cenas": cenas}


def clips_choice(prompt: str, count: int = 3) -> dict[str, Any]:
    """Escolha de cortes de ensaio: o primeiro candidato de cada bloco.

    Le os cabecalhos `### c01 · bloco 1 ...` que a etapa de cortes manda no
    prompt; blocos diferentes nunca se sobrepoem.
    """
    chosen: list[str] = []
    blocks: set[str] = set()
    for candidate, block in re.findall(r"^### (c\d+) · bloco (\d+)", prompt, re.MULTILINE):
        if block in blocks:
            continue
        blocks.add(block)
        chosen.append(candidate)
        if len(chosen) == count:
            break
    return {
        "cortes": [
            {
                "candidato": candidate,
                "gancho": {"pt": f"Gancho de ensaio {n}", "en": f"Rehearsal hook {n}"},
                "legenda": {
                    "pt": f"Corte de ensaio {n}\nTexto de ensaio. O que você acha?",
                    "en": f"Rehearsal clip {n}\nRehearsal text. What do you think?",
                },
                "hashtags": {"pt": ["#historia", "#ensaio"], "en": ["#history", "#rehearsal"]},
            }
            for n, candidate in enumerate(chosen, start=1)
        ],
        "video_inteiro": {
            "legenda": {
                "pt": "Vídeo de ensaio\nO documentário completo de ensaio.",
                "en": "Rehearsal video\nThe full rehearsal documentary.",
            },
            "hashtags": {"pt": ["#historia", "#ensaio"], "en": ["#history", "#rehearsal"]},
        },
    }


def shorten_blocks(prompt: str) -> dict[str, Any]:
    """Encurtamento de ensaio: corta cada bloco EN no limite de palavras."""
    listed = prompt.split("## Blocks", 1)[-1].split("## Rules", 1)[0]
    items = json.loads(listed[listed.index("[") : listed.rindex("]") + 1])
    return {
        "blocos": [
            {
                "indice": item["indice"],
                "narracao": " ".join(item["en"].split()[: item["limite_palavras"]]),
                "palavras": min(len(item["en"].split()), item["limite_palavras"]),
            }
            for item in items
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

        if tem("encurtar"):
            return json.dumps(shorten_blocks(prompt), ensure_ascii=False)

        if tem("storyboard"):
            return json.dumps(_storyboard_v2(prompt), ensure_ascii=False)

        if tem("thumbnail"):
            return json.dumps(
                {
                    "conceito": "composição de ensaio",
                    "descricao_visual": "a single stone arch against an open sky, low angle",
                    "mc": {"acao": "pointing at the arch", "expressao": "curious"},
                    "lado_texto": "esquerda",
                },
                ensure_ascii=False,
            )

        if tem("metadados"):
            #  Capitulos, fontes e aviso sao montados por codigo (etapa 13).
            return json.dumps(
                {
                    "titulo": "Vídeo de ensaio",
                    "titulos_alternativos": ["Ensaio do pipeline", "O pipeline por dentro"],
                    "paragrafos": [
                        "Primeiro parágrafo de ensaio, gerado sem provedor externo.",
                        "Segundo parágrafo de ensaio, com o que o vídeo mostra.",
                    ],
                    "tags": ["ensaio", "pipeline", "teste"],
                    "thumbnail_texto": "ENSAIO",
                },
                ensure_ascii=False,
            )

        if tem("cortes"):
            return json.dumps(clips_choice(prompt), ensure_ascii=False)

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
