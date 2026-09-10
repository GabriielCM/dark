# ADR 0001: Stack do orquestrador e do painel

- **Status:** aceito (aprovado pelo dono do projeto em 10/09/2026, junto com o pedido de implementação)
- **Data:** 10/09/2026
- **Contexto no brief:** seções 7 (arquitetura e operação) e 12 (decisões pendentes)

---

## Contexto

O pipeline transforma um tema em dois vídeos de 12 a 15 minutos. Ele precisa de:

1. **Orquestração com retomada.** Doze etapas por vídeo, algumas caras (LLM, TTS, imagens). Uma falha na etapa 9 não pode reexecutar a etapa 3.
2. **Trabalho pesado na GPU local.** RTX 3060 12 GB, Windows. Alinhamento de legendas, remoção de fundo, mapas de profundidade e geração de cenários (FLUX.1 schnell).
3. **Renderização em Node/TS.** O Remotion não tem alternativa: é Node.
4. **Painel web local.** Fila, revisão do corte final, custos, upload de livros.
5. **Orçamento duro de US$ 50/mês.** Todo gasto passa por um registrador com teto.
6. **Provedores trocáveis** por configuração.

Restrições humanas: um desenvolvedor, menos de 3 h/semana de operação, experiência prévia com Python/FastAPI.

---

## Decisão

**Orquestrador e painel em Python 3.11 + FastAPI. Remotion permanece como um processo Node/TS invocado por linha de comando na etapa de montagem.**

Componentes:

| Camada | Escolha | Por quê |
|---|---|---|
| Linguagem do orquestrador | Python 3.11 | Experiência prévia; é a língua nativa de tudo que roda na GPU (`torch`, `diffusers`, `faster-whisper`, `rembg`, `transformers`) |
| API e painel | FastAPI + Uvicorn | Já conhecido; async nativo para chamar provedores em paralelo |
| Interface do painel | Jinja2 + HTMX + Alpine.js | Sem segundo toolchain de build. O painel é local, para um usuário; um SPA seria custo sem retorno |
| Persistência | SQLite (WAL) via SQLAlchemy 2 | Um usuário, uma máquina. Zero infraestrutura. O arquivo do banco é o backup |
| Fila de etapas | Fila própria em SQLite, worker em processo separado | Ver "Alternativas" abaixo. Celery/RQ exigem Redis, que é ruim no Windows e é infra demais para 3 vídeos/semana |
| Busca vetorial (livros) | Embeddings em SQLite + cosseno com NumPy | Até ~100 mil trechos isso responde em milissegundos. Fica atrás de uma interface: trocar por `sqlite-vec` ou Qdrant é mudar uma classe |
| Renderização | Remotion 4 (Node 20+/TS) chamado via `subprocess` | Fronteira fina e explícita: o Python escreve um JSON de props, o Remotion lê e renderiza |
| Configuração | YAML por canal e por estilo + `.env` para segredos | Segredo nunca em YAML; YAML nunca em código |
| Testes | pytest (Python) + vitest (Remotion, quando houver lógica lá) | |
| Qualidade | ruff (lint e formato) + mypy no núcleo | |

### A fronteira Python ↔ Node

O Python **não** importa nada de Node e o Remotion **não** conhece o banco. O contrato é um arquivo:

```
videos/<video_id>/montagem/props.<lang>.json   →  npx remotion render  →  videos/<video_id>/entrega/video.<lang>.mp4
```

Esse JSON é validado por um modelo Pydantic do lado do Python e por um tipo TypeScript do lado do Remotion. As duas definições vivem lado a lado e há um teste que compara os campos.

### Fila e retomada

Cada vídeo é uma linha em `videos` com um estado. Cada etapa é uma linha em `steps` com estado próprio (`pending`, `running`, `done`, `failed`, `blocked`). O worker:

1. Pega o próximo vídeo cuja etapa atual está `pending` e cujas dependências estão `done`.
2. Marca `running` com um *lease* (timestamp + pid). Lease vencido volta para `pending` — é assim que uma queda do processo se recupera.
3. Executa a etapa. Sucesso grava os artefatos e um sidecar `.meta.json`; falha grava a exceção e incrementa `attempts`.
4. **Idempotência:** antes de executar, a etapa verifica se seus artefatos de saída já existem e estão íntegros. Se sim, marca `done` sem gastar um centavo. É isso que garante "retomar sem repetir chamadas pagas".

Não há paralelismo entre etapas do mesmo vídeo. Há paralelismo *dentro* de uma etapa (gerar 90 cenários) e entre vídeos diferentes, limitado por um semáforo de GPU de tamanho 1.

---

## Alternativas consideradas

### A: tudo em Node/TS

Eliminaria a fronteira de processos e daria um repositório só.

Rejeitada porque empurra todo o trabalho de GPU para fora do processo: `faster-whisper`, `diffusers`/FLUX, `rembg` e Depth Anything são bibliotecas Python. Em Node, cada uma vira uma chamada de subprocesso para... Python. A fronteira não some, só muda de lugar — e para o lado errado, já que o trabalho pesado é o de GPU, não o de renderização. Some também a experiência prévia com FastAPI.

### B: Celery ou RQ para a fila

Rejeitada pelo custo de infra. Ambos exigem Redis; o Redis no Windows é uma porta para o WSL2, e o WSL2 complica o acesso à GPU e ao sistema de arquivos. Para 2 a 3 vídeos por semana, uma fila em SQLite com *lease* resolve o mesmo problema em ~200 linhas testáveis, sem serviço extra para manter ligado.

Se um dia houver mais de uma máquina, essa é a peça a trocar — e ela está isolada em `pipeline/queue.py` justamente por isso.

### C: Prefect ou Temporal

Dão retomada, retentativa e observabilidade de graça, e são a resposta certa numa equipe. Aqui somam um servidor, um modelo mental e uma dependência grande para um pipeline linear de doze etapas operado por uma pessoa. Rejeitadas por desproporção.

### D: painel em React/Vite

O Node já está no repositório por causa do Remotion, então não seria uma dependência nova. Rejeitada mesmo assim: o painel tem cinco telas e um usuário. HTMX entrega as mesmas telas sem um segundo processo de build, sem `node_modules` no caminho da operação e sem estado duplicado entre cliente e servidor. Se o painel virar multiusuário na VPS, reavaliar.

### E: Postgres

Rejeitado enquanto a execução for local. SQLite em modo WAL aguenta com folga um worker e um servidor web. A camada de acesso usa SQLAlchemy justamente para que a migração seja de configuração, não de reescrita.

---

## Consequências

**Boas:**
- Um `uv sync` e um `npm ci` bastam para levantar tudo. Sem Docker obrigatório, sem Redis, sem servidor de banco.
- O código que fala com a GPU é Python direto, sem ponte.
- O núcleo (fila, custos, adaptadores, gate) é testável sem GPU e sem rede — os testes rodam em qualquer CI.
- Trocar de provedor é editar YAML.

**Ruins, e assumidas:**
- Dois gerenciadores de pacote no repositório (`uv` e `npm`). Mitigado por um `Makefile`/`tasks.py` que esconde ambos.
- O contrato de props entre Python e Remotion pode divergir em silêncio. Mitigado pelo teste de contrato.
- SQLite não serve dois workers em máquinas diferentes. Aceito: é explicitamente o cenário de hoje, e a fila está isolada.
- Jinja2 + HTMX envelhece mal se o painel crescer muito. O gatilho de reavaliação é "mais de um usuário simultâneo".

**Não decidido aqui:**
- Provedor de TTS (teste cego, brief 6.1) — o adaptador já existe e o vencedor entra por configuração.
- Modelo de cenários (teste de estilo, brief 5.1) — idem.
- Execução em VPS (brief 12) — nada no orquestrador supõe a máquina local, exceto os provedores marcados como `local: true`.

---

## Como isso vira código

```
src/mundoantigo/
  config.py, paths.py      # YAML + .env, layout de diretórios
  db/                      # modelos SQLAlchemy e sessão
  costs/                   # registrador, tabela de preços, teto mensal
  providers/               # llm, image, tts, align, search — todos atrás de Protocol
  prompts/                 # registro de prompts versionados em arquivo
  pipeline/                # estados, fila, worker, e as 12 etapas
  books/                   # ingestão, classificação de direitos, base vetorial
  render/                  # ponte para o Remotion
  web/                     # FastAPI + templates do painel
render/                    # projeto Remotion (Node/TS)
```
