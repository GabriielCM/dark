# Mundo Antigo

Pipeline que transforma um tema, ou um capitulo de livro, em **dois videos
narrados de 12 a 15 minutos** (PT-BR e EN) para dois canais de historia antiga
no YouTube.

A revisao humana acontece em um unico ponto: o corte final, no painel. O resto
e automatico.

- Contexto e decisoes de produto: [`docs/BRIEF.md`](docs/BRIEF.md)
- Regras para quem programa aqui: [`CLAUDE.md`](CLAUDE.md)
- Decisoes tecnicas: [`docs/decisoes/`](docs/decisoes/)

---

## Comecar

Precisa de **Python 3.11+** e **Node 20+**. Windows com WSL2 funciona; os
provedores locais (FLUX, Kokoro, faster-whisper) precisam de GPU.

```bash
# 1. Dependencias do orquestrador
uv sync --extra dev --extra books

# 2. Dependencias da montagem
cd render && npm ci && cd ..

# 3. Segredos
cp .env.example .env      # preencha as chaves que for usar

# 4. Diretorios e banco
uv run mundoantigo init
```

### Ver o pipeline rodar sem gastar nada

```bash
uv run mundoantigo nova "Como os aquedutos romanos moviam agua sem bombas"
uv run mundoantigo worker --ensaio --uma-vez
uv run mundoantigo status
```

O modo `--ensaio` troca todos os provedores por versoes falsas: percorre as
doze etapas, grava todos os artefatos e nao faz uma unica chamada externa.

### Rodar de verdade

```bash
uv run mundoantigo painel      # http://127.0.0.1:8765
uv run mundoantigo worker      # noutro terminal
```

---

## Como funciona

Cada producao e um roteiro que vira **dois videos**. Pesquisa, checagem de
fatos e imagens servem aos dois idiomas; so a narracao muda.

```
tema ─► pesquisa ─► roteiro + relatorio de fatos ─► GATE ─► adaptacao EN
                                                     │
                                                     ▼
    entrega ◄─ revisao ◄─ metadados ◄─ montagem ◄─ narracao + cenarios ◄─ cenas
```

As doze etapas sao **idempotentes e retomaveis**: se algo falha, o pipeline
retoma da ultima etapa concluida sem repetir chamadas pagas. Ver
[ADR 0002](docs/decisoes/0002-fila-e-retomada.md).

### As tres regras que o codigo faz valer

| Regra | Onde vive | O que acontece |
|---|---|---|
| **Orcamento de US$ 50/mes** | `costs/recorder.py` | Toda chamada paga passa por um `guard` que consulta o teto **antes** de a chamada sair. Atingido o teto, a producao fica `blocked` e retoma quando o mes virar |
| **Gate de fatos** | `pipeline/fact_gate.py` | Um item de baixa confianca bloqueia a renderizacao. O pipeline tenta reescrever sozinho; se nao resolver, escala para humano |
| **Direitos autorais** | `books/rights.py` | Classificacao automatica (BR 70 anos apos a morte; EUA 95 anos apos a publicacao; traducao e obra separada). Na duvida, protegida — entra so como fonte de fatos |

---

## Comandos

```bash
uv run mundoantigo init                  # diretorios, banco e checagem da configuracao
uv run mundoantigo nova "<tema>"         # enfileira uma producao
uv run mundoantigo worker                # executa as etapas da fila
uv run mundoantigo worker --ensaio       # ... com provedores falsos, custo zero
uv run mundoantigo status [<video_id>]   # estado da fila ou de uma producao
uv run mundoantigo custos                # gasto do mes por etapa e por producao
uv run mundoantigo aprovar <video_id>    # aprova o corte final
uv run mundoantigo rejeitar <id> "<motivo>"
uv run mundoantigo refazer <id> <etapa> [--apagar]
uv run mundoantigo livro <arquivo.pdf>   # ingere um livro e classifica os direitos
uv run mundoantigo painel                # sobe o painel web local
```

### Refazer uma etapa

```bash
uv run mundoantigo refazer <video_id> cenas            # reexecuta, mas reaproveita artefatos
uv run mundoantigo refazer <video_id> cenas --apagar   # apaga e refaz de verdade (gasta de novo)
```

Sem `--apagar`, as etapas seguintes voltam para a fila mas quem ja tem artefato
completo e pulado sem custo. Essa e a diferenca entre "retomar" e "refazer".

---

## O painel

`http://127.0.0.1:8765`, cinco telas:

| Tela | Para que |
|---|---|
| **Fila** | Enfileirar tema, ver o andamento e o custo de cada producao |
| **Producao** | As doze etapas, o relatorio de fatos, os artefatos, refazer uma etapa |
| **Revisao** | Corte final: os dois videos de um lado, o relatorio de fatos do outro. Aprovar ou rejeitar com motivo |
| **Custos** | Gasto do mes por etapa e por producao, contra o teto |
| **Livros** | Upload de PDF/ePub, classificacao de direitos com justificativa, capitulos como pauta |

Fora de `127.0.0.1`, `MA_PANEL_AUTH_TOKEN` passa a ser obrigatorio — a
configuracao recusa subir sem ele.

---

## Estrutura

```
config/              canais, estilo visual, precos dos provedores
prompts/             prompts versionados em arquivo (nunca no codigo)
src/mundoantigo/
  costs/             registrador de custos e teto (ADR 0003)
  providers/         llm, imagem, tts, alinhamento, busca — todos atras de adaptador
  pipeline/          maquina de estados, fila, gate de fatos, as 12 etapas
  books/             ingestao, classificacao de direitos, base vetorial
  render/            ponte para o Remotion
  web/               painel FastAPI + templates
render/              projeto Remotion (Node/TS): 2.5D, parallax, legendas
biblioteca/          personagem (SVG), trilhas, sfx — gerados uma unica vez
videos/<video_id>/   artefatos de cada producao, por etapa
```

### Trocar de provedor

Editar `config/app.yaml`. Nada mais:

```yaml
provedores:
  tts:
    padrao: elevenlabs      # era kokoro
```

Todo provedor pago precisa de preco em `config/precos.yaml` — sem isso o
registrador bloqueia a chamada. Friccao deliberada ([ADR 0003](docs/decisoes/0003-custos-e-teto.md)).

---

## Testes

```bash
uv run pytest              # 206 testes, ~10 s, sem rede e sem GPU
uv run pytest -m slow      # + render de verdade no Remotion (exige npm ci)
uv run ruff check src tests
uv run mypy
```

O conjunto padrao cobre o pipeline de ponta a ponta com provedores falsos,
incluindo um video-exemplo de ~60 s, a retomada sem repetir chamadas pagas e o
contrato de props entre Python e Remotion.

---

## Estado do projeto

Pronto: esqueleto, registrador de custos, adaptadores, as doze etapas, gate de
fatos, classificacao de direitos, painel, montagem no Remotion.

Aguardando decisao (brief, secao 12):

- **Estilo visual** — `config/estilo/guia.yaml` esta `provisorio` ate o teste de estilo
- **Voz** — o adaptador esta pronto; o vencedor do teste cego entra em `config/app.yaml`
- **Personagem** — `biblioteca/personagem/` vazia; as cenas saem sem ele ate a biblioteca existir
- **Trilhas e efeitos** — `biblioteca/trilhas/` e `biblioteca/sfx/` vazias
