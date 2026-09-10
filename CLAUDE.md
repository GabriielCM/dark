# CLAUDE.md: canais dark "Mundo Antigo"

O contexto completo e as decisões de produto estão no brief. Leia antes de propor qualquer arquitetura:
@docs/BRIEF.md

## O que é

Um pipeline que transforma um tema, ou um capítulo de livro, em **dois vídeos narrados de 12 a 15 minutos** (PT-BR e EN), em estilo cartunesco, para dois canais do YouTube de história antiga.

A revisão humana acontece em um único ponto: o corte final, feito no painel web. O resto é automático.

## Restrições que não mudam sem aprovação

- **Orçamento de US$ 50/mês para todas as APIs.**
  - Toda chamada paga passa por um registrador de custos (etapa, provedor, modelo, valor, `video_id`).
  - Um teto mensal configurável bloqueia chamadas pagas quando é atingido.
- **Local primeiro.**
  - O que couber roda na máquina local: Windows, RTX 3060 12 GB. Valide a compatibilidade e use WSL2 ou Docker se necessário.
  - Prefira modelos locais a APIs pagas.
- **Montagem 100% automática** com Remotion (Node/TS) e FFmpeg.
- **Provedores:**
  - LLM e imagens via OpenRouter.
  - TTS atrás de adaptador; o provedor será definido no teste cego.
  - Todo provedor (texto, imagem, voz, alinhamento) fica atrás de um adaptador. Trocar de provedor deve ser só trocar a configuração.
- **Direitos autorais:** nunca adaptar nem narrar obra protegida. Regras no brief, seção 4.
- **Gate de fatos:** nenhuma renderização sem relatório de fatos aprovado. Um item de baixa confiança bloqueia a etapa.
- **Originalidade visual:** não gerar conteúdo que imite personagens, marcas ou estilos de estúdios e artistas existentes.
- **Segurança:**
  - Segredos ficam em `.env`, que nunca é commitado.
  - Se o painel for exposto fora da rede local, HTTPS e autenticação passam a ser obrigatórios.

## Etapas do pipeline

Cada vídeo é uma máquina de estados. As etapas são **idempotentes e retomáveis**: se algo falhar, o pipeline retoma da última etapa concluída sem repetir chamadas pagas.

| # | Etapa | O que faz |
|---|---|---|
| 1 | `pauta` | Tema vindo de lista manual, sugestão automática ou capítulo de livro |
| 2 | `pesquisa` | Busca web e base de livros; gera um dossiê com fontes |
| 3 | `roteiro` | Roteiro PT-BR (template com variações, tom documental) e relatório de fatos |
| 4 | `gate_fatos` | Bloqueia se houver item de baixa confiança; tenta reescrever antes de escalar para humano |
| 5 | `adaptacao_en` | Adapta o roteiro aprovado para inglês (não é tradução literal) |
| 6 | `cenas` | Storyboard: cenas, duração, prompt do cenário, pose do personagem |
| 7 | `assets` | Cenários raster (local primeiro); personagem vem da biblioteca SVG |
| 8 | `narracao` | TTS em PT e EN; alinhamento local gera timestamps e os SRTs |
| 9 | `montagem` | Remotion: 2.5D, vetores animados, trilha e efeitos da biblioteca; render 16:9 PT e EN |
| 10 | `metadados` | Título, descrição com fontes, tags, capítulos, thumbnail |
| 11 | `revisao` | Painel: corte final com relatório de fatos; aprovar ou rejeitar com motivo |
| 12 | `entregue` | Pacote pronto para upload manual no YouTube |

O pipeline de livros é separado: ingestão (PDF/ePub, OCR), identificação, classificação de direitos, base vetorial e geração de pautas por capítulo.

## Estrutura de dados (proposta, ajustável no ADR)

```
config/
  canais/pt-br.yaml    # voz, idioma, template narrativo, prompts-base
  canais/en.yaml
  estilo/              # guia de estilo, referências, prompt-base visual
prompts/               # prompts versionados em arquivo, nunca hardcoded
biblioteca/
  personagem/          # SVGs de poses e expressões, partes separadas
  trilhas/             # música, com licença registrada
  sfx/
livros/                # arquivos ingeridos, metadados, classificação de direitos
videos/<video_id>/     # artefatos por etapa e estado atual
docs/
  BRIEF.md
  decisoes/            # ADRs numerados
```

## Convenções

- **Idioma:** código, identificadores e commits em inglês. Documentação e interface do painel em PT-BR.
- **Rastreabilidade:** todo artefato gerado guarda um sidecar de metadados com modelo, provedor, versão do prompt, custo, seed (quando houver) e data.
- **Testes:**
  - unitários para adaptadores, registrador de custos, gate de fatos e classificação de direitos
  - um vídeo-exemplo de cerca de 60 s como teste de ponta a ponta barato
- **Cautela com gastos:** antes de adicionar um provedor pago novo ou uma etapa que gere custo recorrente, estime o impacto mensal e peça confirmação.

## Estado

A stack foi decidida em [ADR 0001](docs/decisoes/0001-stack.md): orquestrador e painel em Python 3.11 + FastAPI, Remotion como processo Node/TS chamado na montagem. As doze etapas, o registrador de custos, os adaptadores, o gate de fatos, a classificação de direitos e o painel estão implementados.

O que falta depende de decisões que não são de código (brief, seção 12): estilo visual, voz, personagem e bibliotecas de trilha e efeito. Os lugares que esperam por elas estão marcados:

- `config/estilo/guia.yaml` — `status: provisorio` até o teste de estilo
- `config/app.yaml`, bloco `provedores.tts` — o vencedor do teste cego entra aqui
- `biblioteca/personagem/` — vazia; as cenas saem sem o personagem enquanto for assim

## Comandos

```bash
uv sync --extra dev --extra books      # dependências do orquestrador
cd render && npm ci && cd ..           # dependências da montagem
uv run mundoantigo init                # diretórios, banco e checagem da configuração
```

Operação:

```bash
uv run mundoantigo nova "<tema>"              # enfileira uma produção
uv run mundoantigo worker                     # executa as etapas da fila
uv run mundoantigo worker --ensaio --uma-vez  # percorre o pipeline sem gastar nada
uv run mundoantigo painel                     # painel em http://127.0.0.1:8765
uv run mundoantigo status [<video_id>]
uv run mundoantigo custos
uv run mundoantigo refazer <id> <etapa> [--apagar]
uv run mundoantigo livro <arquivo.pdf>
```

Qualidade:

```bash
uv run pytest              # sem rede, sem GPU, sem gasto
uv run pytest -m slow      # + render de verdade no Remotion
uv run ruff check src tests && uv run ruff format src tests
uv run mypy
cd render && npm run typecheck
```

## Onde mexer

| Para... | Vá em |
|---|---|
| mudar um prompt | `prompts/<etapa>/<nome>.v<N>.md` — nova versão é arquivo novo, nunca edição silenciosa |
| trocar de provedor | `config/app.yaml`, bloco `provedores` (e o preço em `config/precos.yaml`) |
| ajustar o ritmo das imagens | `config/app.yaml`, bloco `cenas` |
| mudar uma etapa | `src/mundoantigo/pipeline/steps/sNN_<nome>.py` |
| mexer na montagem | `render/src/` — e atualize `render/src/types.ts` junto com `src/mundoantigo/render/props.py` |

Adicionar um provedor pago exige adicionar o preço em `config/precos.yaml`: sem preço, o registrador bloqueia a chamada. É de propósito.

## Pendências que afetam o código

- Provedor de TTS (teste cego), com adaptador pronto antes da escolha
- Estilo visual e modelo de cenários (teste de estilo)
- Ritmo de troca de imagens: começar com 8 a 10 s, configurável
- Execução local ou em servidor no médio prazo: não acoplar o orquestrador à máquina

A lista completa está no brief, seção 12.
