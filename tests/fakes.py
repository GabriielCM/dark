"""Respostas de LLM para os testes de ponta a ponta.

Um roteiro curto de verdade: o CLAUDE.md pede "um video-exemplo de cerca de
60 s como teste de ponta a ponta barato". Estas respostas produzem exatamente
isso, sem rede e sem GPU.
"""

from __future__ import annotations

import json
import re
from typing import Any

#  O FakeTTS gera ~13 caracteres por segundo. Tres repeticoes dao ~60 s, que
#  e o tamanho do video-exemplo pedido pelo CLAUDE.md — e casa com as 7 cenas
#  de 8,6 s do storyboard abaixo, sem disparar o aviso de ritmo.
NARRACAO_PT = (
    "A agua chegava a Roma sem nenhuma bomba. "
    "Os engenheiros romanos resolveram o problema com uma unica ideia: inclinacao constante. "
    "Um aqueduto descia poucos centimetros a cada cem metros, e essa queda minima bastava "
    "para mover milhoes de litros por dia. "
) * 3

NARRACAO_EN = (
    "Water reached Rome without a single pump. "
    "Roman engineers solved the problem with one idea: a constant gradient. "
    "An aqueduct dropped a few inches every hundred yards, and that tiny fall was enough "
    "to move millions of gallons a day. "
) * 3

FONTES = [
    {
        "id": "f1",
        "titulo": "Roman Aqueducts",
        "url": "https://cambridge.org/aqueducts",
        "tipo": "academica",
        "ano": 2018,
    },
    {
        "id": "f2",
        "titulo": "Water in the Ancient City",
        "url": "https://jstor.org/water",
        "tipo": "academica",
        "ano": 2015,
    },
]

DOSSIE = {
    "tema": "Aquedutos romanos",
    "resumo": "Como a agua chegava a Roma usando so gravidade.",
    "angulo": "A inclinacao, e nao os arcos, e a engenharia de verdade.",
    "blocos": [
        {
            "titulo": "A inclinacao",
            "conteudo": "Queda constante ao longo de dezenas de quilometros.",
            "afirmacoes": [
                {
                    "texto": "Os aquedutos funcionavam por gravidade.",
                    "fontes": ["f1", "f2"],
                    "tipo": "consenso",
                },
            ],
        }
    ],
    "lacunas": [],
    "fontes": FONTES,
}


def _blocos_no_prompt(prompt: str) -> int:
    """Quantos blocos tem o roteiro PT que veio no prompt de adaptacao."""
    return max(1, prompt.split("## Target")[0].count('"secao"'))


def _roteiro_em_blocos(narracao: str, titulo: str, n: int) -> dict:
    """Roteiro com exatamente `n` blocos: a adaptacao nunca muda a estrutura."""
    palavras = narracao.split()
    tamanho = max(1, len(palavras) // n)
    blocos = []
    for i in range(n):
        parte = palavras[i * tamanho : (i + 1) * tamanho if i < n - 1 else None]
        blocos.append(
            {
                "secao": "gancho" if i == 0 else "desenvolvimento",
                "titulo": f"Part {i + 1}",
                "narracao": " ".join(parte) or "More on this.",
                "afirmacoes_usadas": ["a1"] if i == 0 else ["a2"] if i == 1 else [],
            }
        )
    return {
        "titulo_provisorio": titulo,
        "blocos": blocos,
        "pedidos_de_pesquisa": [],
        "palavras_total": len(palavras),
    }


def _roteiro(narracao: str, titulo: str) -> dict:
    metade = len(narracao) // 2
    return {
        "titulo_provisorio": titulo,
        "gancho": narracao[:80],
        "blocos": [
            {
                "secao": "gancho",
                "titulo": "A agua sem bomba",
                "narracao": narracao[:metade].strip(),
                "afirmacoes_usadas": ["a1"],
            },
            {
                "secao": "desenvolvimento",
                "titulo": "A inclinacao",
                "narracao": narracao[metade:].strip(),
                "afirmacoes_usadas": ["a2"],
            },
        ],
        "pedidos_de_pesquisa": [],
        "palavras_total": len(narracao.split()),
    }


RELATORIO_APROVADO = {
    "itens": [
        {
            "id": "a1",
            "afirmacao": "Os aquedutos funcionavam por gravidade.",
            "bloco": 0,
            "fontes": ["https://cambridge.org/aqueducts", "https://jstor.org/water"],
            "confianca": "alta",
            "justificativa": "duas fontes academicas concordam",
        },
        {
            "id": "a2",
            "afirmacao": "A queda era de poucos centimetros por cem metros.",
            "bloco": 1,
            "fontes": ["https://cambridge.org/aqueducts", "https://jstor.org/water"],
            "confianca": "alta",
            "justificativa": "medido em aquedutos preservados",
        },
    ]
}

RELATORIO_REPROVADO = {
    "itens": [
        {
            "id": "a1",
            "afirmacao": "Os aquedutos funcionavam por gravidade.",
            "bloco": 0,
            "fontes": ["https://cambridge.org/aqueducts", "https://jstor.org/water"],
            "confianca": "alta",
            "justificativa": "ok",
        },
        {
            "id": "a2",
            "afirmacao": "Roma tinha exatamente 11 aquedutos em 100 a.C.",
            "bloco": 1,
            "fontes": [],
            "confianca": "baixa",
            "justificativa": "nenhuma fonte do dossie sustenta o numero",
            "correcao_sugerida": "dizer que eram varios, sem numero exato",
        },
    ]
}


_TIPOS = ("atuada", "lugar", "plano_detalhe", "cartao", "metafora", "plano_geral")
_CAMERAS = ("zoom_in", "pan_left", "estatica", "zoom_out", "pan_right")


def storyboard_v2(prompt: str) -> dict[str, Any]:
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


#  Formato v2 (prompts/metadados/pacote.v2.md): capitulos, fontes e aviso
#  sao montados por codigo, nao pelo modelo.
METADADOS = {
    "titulo": "A água que subia sozinha",
    "titulos_alternativos": ["Como a água chegava a Roma", "O segredo era a inclinação"],
    "paragrafos": [
        "Como os aquedutos romanos moviam milhões de litros sem uma única bomba?",
        "A resposta está numa queda de poucos centímetros a cada cem metros.",
    ],
    "tags": ["roma antiga", "aquedutos", "engenharia romana", "história"],
    "thumbnail_texto": "SEM BOMBAS",
}

THUMBNAIL = {
    "conceito": "arco de aqueduto contra o céu",
    "descricao_visual": "single aqueduct arch against open sky, low angle",
    "mc": {"acao": "looking up at the arch", "expressao": "amazed"},
    "lado_texto": "direita",
}


def responder(*, gate_reprova_uma_vez: bool = False):
    """Devolve uma funcao que responde conforme o prompt recebido.

    `gate_reprova_uma_vez` faz a primeira checagem reprovar, para exercitar a
    reescrita automatica do gate.
    """
    estado = {"checagens": 0}

    def responde(prompt: str) -> str:
        if "Monte um dossiê" in prompt:
            return json.dumps(DOSSIE, ensure_ascii=False)
        if "verificador de fatos" in prompt:
            estado["checagens"] += 1
            reprova = gate_reprova_uma_vez and estado["checagens"] == 1
            return json.dumps(
                RELATORIO_REPROVADO if reprova else RELATORIO_APROVADO, ensure_ascii=False
            )
        if "roteiros de documentário" in prompt:
            return json.dumps(_roteiro(NARRACAO_PT, "A agua que subia sozinha"), ensure_ascii=False)
        if "reescreva" in prompt.lower() or "Reescreva" in prompt:
            return json.dumps(
                {
                    "correcoes": [
                        {
                            "id": "a2",
                            "acao": "qualificar",
                            "texto_antigo": "Roma tinha exatamente 11 aquedutos em 100 a.C.",
                            "texto_novo": "Roma foi acumulando aquedutos ao longo de seculos.",
                            "motivo": "o numero exato nao tem fonte",
                        }
                    ]
                },
                ensure_ascii=False,
            )
        if "Adapt this Brazilian" in prompt:
            roteiro = _roteiro_em_blocos(
                NARRACAO_EN, "The water that climbed", _blocos_no_prompt(prompt)
            )
            return json.dumps(roteiro, ensure_ascii=False)
        if "Quebre o roteiro" in prompt:
            return json.dumps(storyboard_v2(prompt), ensure_ascii=False)
        if "Proponha a thumbnail" in prompt:
            return json.dumps(THUMBNAIL, ensure_ascii=False)
        if "metadados de publicação" in prompt:
            return json.dumps(METADADOS, ensure_ascii=False)
        if "dados bibliográficos" in prompt:
            return json.dumps(
                {
                    "titulo": "Historia de Roma",
                    "autor": "Autor Antigo",
                    "autor_ano_morte": 1900,
                    "tradutor": None,
                    "idioma": "pt",
                    "ano_publicacao_original": 1890,
                    "ano_desta_edicao": 1890,
                    "capitulos": [{"numero": 1, "titulo": "A fundacao", "pagina_inicial": 1}],
                    "confianca": "alta",
                    "observacoes": "",
                },
                ensure_ascii=False,
            )
        return json.dumps({"ok": True}, ensure_ascii=False)

    return responde
