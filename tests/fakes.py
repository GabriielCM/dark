"""Respostas de LLM para os testes de ponta a ponta.

Um roteiro curto de verdade: o CLAUDE.md pede "um video-exemplo de cerca de
60 s como teste de ponta a ponta barato". Estas respostas produzem exatamente
isso, sem rede e sem GPU.
"""

from __future__ import annotations

import json

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


def storyboard(n_cenas: int = 7) -> dict:
    """Sete cenas de ~9 s cobrem os 60 s do video de teste."""
    return {
        "cenas": [
            {
                "indice": i,
                "narracao": f"trecho {i}",
                "duracao_estimada_s": 8.6,
                "prompt_cenario": f"roman aqueduct crossing a dry valley, view {i}",
                "camadas": {"frente": "stone blocks", "meio": "arches", "fundo": "hills"},
                "camera": ["zoom_in", "pan_left", "estatica", "zoom_out"][i % 4],
                "personagem": {"pose": "apontando", "posicao": "direita"} if i % 4 == 0 else None,
                "sfx": None,
                "musica": "descoberta",
            }
            for i in range(1, n_cenas + 1)
        ]
    }


METADADOS = {
    "titulo": "A agua que subia sozinha",
    "titulos_alternativos": ["Como a agua chegava a Roma"],
    "descricao": "Como os aquedutos romanos moviam milhoes de litros sem uma unica bomba.",
    "tags": ["roma antiga", "aquedutos", "engenharia romana", "historia"],
    "capitulos": [
        {"tempo": "00:00", "titulo": "A agua sem bomba"},
        {"tempo": "00:30", "titulo": "A inclinacao"},
    ],
    "thumbnail": {
        "conceito": "arco de aqueduto contra o ceu",
        "prompt": "single aqueduct arch against open sky, low angle",
        "texto": "SEM BOMBAS",
        "versao_sem_texto": True,
    },
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
            return json.dumps(_roteiro(NARRACAO_EN, "The water that climbed"), ensure_ascii=False)
        if "Quebre o roteiro" in prompt:
            return json.dumps(storyboard(), ensure_ascii=False)
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
