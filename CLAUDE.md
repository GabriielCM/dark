# CLAUDE.md: canais dark "Mundo Antigo"

O contexto completo e as decisões de produto estão no brief. Leia antes de propor qualquer arquitetura:
@docs/BRIEF.md

## O que é

Um pipeline que transforma um tema, ou um capítulo de livro, em **dois vídeos narrados de cerca de 20 minutos** (18 a 22; PT-BR e EN), em estilo cartunesco, para dois canais do YouTube de história antiga.

Em teste desde 06/10/2026 ([ADR 0011](docs/decisoes/0011-faixa-unica-de-audio.md)): o canal EN fica parado, e o vídeo PT sobe com a narração EN como segunda faixa de áudio. As duas narrações dividem a mesma linha do tempo (`narracao.faixa_unica` no `app.yaml`).

Desde 06/10/2026 há também duas contas no TikTok, PT e EN ([ADR 0010](docs/decisoes/0010-cortes-tiktok.md)). Desde 08/10, a conta EN está parada: o primeiro corte em inglês foi visto 96% no Brasil. Cada vídeo rende 6 cortes verticais PT de 65 a 100 s, de trechos diferentes, e o vídeo inteiro fica fixado no perfil PT. A quantidade por conta fica em `tiktok.cortes`, em `config/canais/*.yaml`.

A esteira é mista (alinhamento de 09/2026):
- **Na sessão do Claude Code:** pesquisa, roteiro PT, relatório de fatos, pré-checagem das imagens e pedidos de refação.
- **No worker:** o resto.

O usuário acompanha cada produção pela página dela no navegador (as etapas em lista, com aviso do Windows quando precisa dele; [ADR 0009](docs/decisoes/0009-esteira-e-pagina-da-producao.md)). Siga a skill `.claude/skills/esteira/SKILL.md`. A revisão humana acontece em dois pontos, os dois na página:
1. a grade de imagens: aprovar todas, ou refazer com um link de referência ou com o motivo;
2. o corte final, com o relatório de fatos ao lado.

## Restrições que não mudam sem aprovação

- **Orçamento de US$ 50/mês para todas as APIs.**
  - Toda chamada paga passa por um registrador de custos (etapa, provedor, modelo, valor, `video_id`).
  - Um teto mensal configurável bloqueia chamadas pagas quando é atingido.
- **Local primeiro.**
  - O que couber roda na máquina local: Windows, RTX 3060 12 GB. Valide a compatibilidade e use WSL2 ou Docker se necessário.
  - Prefira modelos locais a APIs pagas.
- **Montagem 100% automática** com Remotion (Node/TS) e FFmpeg.
- **Provedores:**
  - LLM via OpenRouter, com modelos baratos, para a adaptação EN, o storyboard e os metadados. Pesquisa, roteiro PT e relatório de fatos são feitos na sessão e importados, e o custo por vídeo caiu de ~US$ 3 para ~US$ 0,35.
  - Cenários com Z-Image Turbo no ComfyUI local ([ADR 0005](docs/decisoes/0005-comfyui-z-image.md)). Fotos de referência só do Wikimedia Commons ([ADR 0006](docs/decisoes/0006-referencias-commons.md)).
  - Voz com Kokoro local: `pm_santa` a 0,9 no PT e `am_michael` a 1,0 no EN, identificadas nos vídeos entregues.
  - Todo provedor (texto, imagem, voz, alinhamento, referências) fica atrás de um adaptador. Trocar de provedor deve ser só trocar a configuração.
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
| 2 | `pesquisa` | Dossiê com afirmações e fontes. No modo `sessao`, importado da sessão |
| 3 | `roteiro` | Roteiro PT-BR em segunda pessoa, com títulos de capítulo, balões do MC e tarjas, e o relatório de fatos. No modo `sessao`, importado |
| 4 | `gate_fatos` | Bloqueia se houver item de baixa confiança. No modo `sessao`, a correção é feita na sessão |
| 5 | `adaptacao_en` | Adapta o roteiro aprovado para inglês (não é tradução literal), incluindo o texto das camadas |
| 6 | `narracao` | Kokoro frase a frase em PT e EN, tempos de cada frase e de cada palavra, e SRT igual ao roteiro |
| 7 | `cenas` | Storyboard: cenas de ~6 s (4 a 8) cortadas pela duração real da narração, tipo, camadas e o conceito da thumbnail ([ADR 0008](docs/decisoes/0008-narracao-antes-das-cenas.md)) |
| 8 | `referencias` | Fotos do Commons com licença e proporção aceitas, para img2img de lugar, peça e detalhe |
| 9 | `assets` | Cenários no ComfyUI, poses do MC recortadas e a arte base da thumbnail |
| 10 | `pre_checagem` | Marca imagens suspeitas (a parte automática ainda falta: a sessão confere as imagens) |
| 11 | `revisao_imagens` | Revisão humana 1: a grade na página, por capítulo; refazer com link (o worker aplica) ou motivo (a sessão reescreve), ou aprovar todas |
| 12 | `trilha` | Música por clima e efeitos (fase D; hoje o vídeo sai só com a voz) |
| 13 | `metadados` | Título, descrição montada por código, tags, capítulos e thumbnails ([ADR 0007](docs/decisoes/0007-publicacao.md)) |
| 14 | `montagem` | Remotion: 2.5D, camadas de texto, MC recortado, balões e cartões; render 16:9 PT e EN |
| 15 | `cortes` | Cortes verticais do TikTok: o código mede os trechos que cabem, o LLM barato escolhe os de cada conta (hoje 6 no PT e nenhum no EN, que está parado), sem repetir trecho, e escreve gancho, legenda e hashtags, e o Remotion renderiza em 1080x1920 ([ADR 0010](docs/decisoes/0010-cortes-tiktok.md)) |
| 16 | `revisao` | Revisão humana 2: corte final na página, com relatório de fatos, os cortes do TikTok e comentários por momento do vídeo ou do corte; aprovar |
| 17 | `entregue` | Pasta por idioma pronta para o upload manual no YouTube, e `tiktok/<idioma>/` com os cortes da conta, o vídeo inteiro (só no PT) e as legendas |

A narração vem antes do storyboard, que corta as cenas pela duração real de cada frase. A dependência é só de ordem: refazer a voz não refaz as cenas nem as imagens. A trilha anda enquanto a grade de imagens espera revisão. Os cortes saem das cenas, não do mp4: refazer a montagem não refaz os cortes.

O pipeline de livros é separado: ingestão (PDF/ePub, OCR), identificação, classificação de direitos, base vetorial e geração de pautas por capítulo.

## Estrutura de dados (proposta, ajustável no ADR)

```
config/
  canais/pt-br.yaml    # voz, idioma, template narrativo, prompts-base
  canais/en.yaml
  estilo/              # guia de estilo, referências, prompt-base visual
prompts/               # prompts versionados em arquivo, nunca hardcoded
biblioteca/
  personagem/          # conjuntos de poses do MC recortadas, por figurino
  trilhas/             # música, com licença registrada (fase D)
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

A stack foi decidida em [ADR 0001](docs/decisoes/0001-stack.md): orquestrador e painel em Python 3.11 + FastAPI, Remotion como processo Node/TS chamado na montagem.

**Histórico:** o trabalho feito depois de 10/09/2026 se perdeu numa falha de disco, sem commit, e foi reconstruído em 29/09 a partir dos vídeos entregues (`docs/estilo/analise-entregas.md`). Desde então, cada fase termina com commit, push e backup diário no D: ([ADR 0004](docs/decisoes/0004-backup-local.md)).

**Feito:**
- Fase A: ambiente, backup e análise dos vídeos.
- Fase B, paridade com as entregas, que já cobre:
  - as etapas e a refação por etapa;
  - o estilo b-sombreado aprovado e as vozes identificadas;
  - a importação da sessão e a narração frase a frase;
  - o storyboard v2, as camadas do Remotion e as referências do Commons;
  - a publicação.
- Fase C, a esteira (05/10, [ADR 0009](docs/decisoes/0009-esteira-e-pagina-da-producao.md)): a página da produção em lista, a grade de imagens com refazer por link ou motivo, os comentários do corte final, os avisos do Windows, o lançador e a skill da sessão.
- Cortes do TikTok (06/10, [ADR 0010](docs/decisoes/0010-cortes-tiktok.md)): a etapa `cortes`, o layout vertical no Remotion, os cortes no corte final e a pasta `tiktok/` na entrega.

**Falta:**
- Fase C: a pré-checagem automática das imagens (CLIP, OCR, sonda de anacronismo).
- Fase D: trilha e efeitos, só da YouTube Audio Library.

## Comandos

```bash
uv sync --extra dev --extra books      # dependências do orquestrador
uv sync --extra dev --extra books --extra local-gpu --extra voz-id --extra windows  # máquina com GPU
cd render && npm ci && cd ..           # dependências da montagem
uv run mundoantigo init                # diretórios, banco e checagem da configuração
```

Instalação no Windows (uv, Node 22, FFmpeg, ComfyUI e pesos do Z-Image): ver o README. O ComfyUI fica em `C:\dev\ComfyUI` e os pesos em `C:\dev\modelos`.

Operação:

```bash
uv run mundoantigo nova "<tema>" --pilar <pilar>   # enfileira, sobe a esteira e abre a página da produção
uv run mundoantigo esteira [<id>] [--status|--parar]  # ComfyUI, painel e worker destacados; abre a página
uv run mundoantigo nova "<tema>" --roteiro-da-sessao <pasta>  # valida e enfileira com o roteiro da sessão
uv run mundoantigo importar-roteiro <id> <pasta> [--validar-apenas]  # reimporta depois de corrigir
uv run mundoantigo worker                     # executa as etapas da fila
uv run mundoantigo worker --ensaio --uma-vez  # percorre o pipeline sem gastar nada
uv run mundoantigo painel                     # painel em http://127.0.0.1:8765
uv run mundoantigo status [<video_id>]
uv run mundoantigo custos
uv run mundoantigo aprovar <id> [--etapa revisao_imagens]
uv run mundoantigo refazer <id> <etapa> [--apagar]
uv run mundoantigo livro <arquivo.pdf>
uv run mundoantigo backup                     # espelha banco, vídeos, bibliotecas e modelos no D:
```

A sessão conversa com o revisor pela página (detalhes na skill `esteira`):

```bash
uv run mundoantigo aguardar <id> --timeout 6000   # vigia em segundo plano: resposta, pedido com motivo, comentário
uv run mundoantigo perguntar <id> "texto" --opcao A --opcao B   # pergunta no topo da página, com aviso
uv run mundoantigo respostas <id> [--pergunta N --esperar]
uv run mundoantigo nota <id> --etapa pesquisa "texto"            # andamento da sessão na página
uv run mundoantigo imagens pedidos|descrever|refazer|recusar|aplicar <id> ...
uv run mundoantigo corte comentarios|resolver <id> ...
uv run mundoantigo cortes listar <id> [--candidatos]   # cortes do TikTok: trecho, gancho, legenda
uv run mundoantigo cortes editar <id> <n> [--candidato c07] [--gancho-pt ...] [--legenda-en ...]  # sem chamar o LLM
uv run mundoantigo notificar [<id>]               # aviso de teste (som e clique)
```

Os arquivos da sessão (`dossie.json`, `roteiro.pt-br.json` e `relatorio_fatos.json`) ficam em `data/sessao/<tema>/`. O formato está em `src/mundoantigo/session/schemas.py`.

Estilo e voz, usados nas calibrações:

```bash
uv run mundoantigo estilo calibrar [--variantes a,b] [--cenas 01,09]  # folhas lado a lado com o teste antigo
uv run mundoantigo personagem poses --figurino "<figurino em inglês>"
uv run mundoantigo voz identificar <video.mp4>         # qual voz do Kokoro narrou um vídeo
uv run mundoantigo voz aplicar <canal> <voz> --velocidade 0.9
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
| mudar a página da produção | `src/mundoantigo/web/` (rotas em `routes/production.py` e `review.py`, corpos em `templates/etapas/`, `static/painel.js`) |
| mudar a grade, os pedidos ou o corte | `src/mundoantigo/review/images.py` e `final_cut.py`; perguntas e vigia em `conversation/` |
| mudar os avisos ou a esteira | `src/mundoantigo/notify/` e `ops/esteira.py`; blocos `notificacoes` e `esteira` do `config/app.yaml` |
| mudar os cortes do TikTok | `src/mundoantigo/clips/` (candidatos e conferência), `render/clips.py`, `s15_cortes.py`, `prompts/cortes/`; layout em pé em `render/src/layout.ts`; bloco `cortes` do `config/app.yaml` e `tiktok` em `config/canais/*.yaml`, onde ficam a quantidade de cada conta (`cortes`, 0 para a conta parada) e o vídeo inteiro ([ADR 0010](docs/decisoes/0010-cortes-tiktok.md)) |
| mudar a faixa única (pausas, limite de palavras EN) | `src/mundoantigo/text/shared_timeline.py`, `s05_adaptacao_en.py`, `s06_narracao.py`; bloco `narracao` do `config/app.yaml` ([ADR 0011](docs/decisoes/0011-faixa-unica-de-audio.md)) |
| mudar a descrição, a thumb ou o pacote | `src/mundoantigo/publishing/`; os textos fixos (aviso, rótulos) ficam em `config/canais/*.yaml`, bloco `publicacao.textos` ([ADR 0007](docs/decisoes/0007-publicacao.md)) |

Adicionar um provedor pago exige adicionar o preço em `config/precos.yaml`: sem preço, o registrador bloqueia a chamada. É de propósito.

## Pendências que afetam o código

Resolvidas em 09/2026:
- **Voz:** Kokoro `pm_santa` e `am_michael`.
- **Estilo:** b-sombreado com Z-Image Turbo.
- **Ritmo:** cerca de 6 s por imagem, de 4 a 8 s, como nos vídeos entregues (`config/app.yaml`, bloco `cenas`; [ADR 0008](docs/decisoes/0008-narracao-antes-das-cenas.md)).

Ainda abertas:
- Execução local ou em servidor no médio prazo: não acoplar o orquestrador à máquina.
- Trilha e efeitos (fase D): catálogo com licença registrada e mixagem com ducking.

A lista completa está no brief, seção 12.
