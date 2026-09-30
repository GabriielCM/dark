# Mundo Antigo

Pipeline que transforma um tema, ou um capitulo de livro, em **dois videos
narrados de cerca de 20 minutos** (PT-BR e EN) para dois canais de historia
antiga no YouTube.

A pesquisa, o roteiro PT e o relatorio de fatos sao feitos na sessao do Claude
Code e importados; o resto roda no worker. A revisao humana acontece em dois
pontos, no painel: a grade de imagens e o corte final.

- Contexto e decisoes de produto: [`docs/BRIEF.md`](docs/BRIEF.md)
- Regras para quem programa aqui: [`CLAUDE.md`](CLAUDE.md)
- Decisoes tecnicas: [`docs/decisoes/`](docs/decisoes/)

---

## Comecar

Precisa de **Python 3.11+**, **Node 22+** e **FFmpeg**. Os provedores locais
(Z-Image no ComfyUI, Kokoro, faster-whisper) precisam de GPU NVIDIA.

### Maquina de producao (Windows, tudo no nivel do usuario, sem admin)

```powershell
winget install --id astral-sh.uv -e          # uv (e com ele o Python 3.11)
winget install --id Gyan.FFmpeg -e           # ffmpeg e ffprobe
# Node 22: zip portatil de nodejs.org/dist em C:\dev\tools, pasta no PATH do usuario
uv python install 3.11
```

- **ComfyUI:** baixe o `ComfyUI_windows_portable_nvidia.7z` da pagina de
  releases do ComfyUI, extraia com `tar -xf` e renomeie a pasta para
  `C:\dev\ComfyUI`. Os pesos ficam fora dele, em `C:\dev\modelos`, apontados
  por `ComfyUI\extra_model_paths.yaml`.
- **Pesos do Z-Image Turbo** (`huggingface.co/Comfy-Org/z_image_turbo`,
  `split_files/`):
  - `diffusion_models/z_image_turbo_int8_convrot.safetensors` (padrao; 26 s
    por imagem em 1920×1088 na 3060)
  - `text_encoders/qwen_3_4b_fp8_mixed.safetensors`
  - `vae/ae.safetensors`
- **Backup diario** para o disco D: (ADR 0004):
  `powershell -ExecutionPolicy Bypass -File scripts\registrar-tarefas.ps1`

```bash
# 1. Dependencias do orquestrador (na maquina com GPU, acrescente os extras)
uv sync --extra dev --extra books
uv sync --extra dev --extra books --extra local-gpu --extra voz-id --extra windows

# 2. Dependencias da montagem (e o navegador que o Remotion usa)
cd render && npm ci && npx remotion browser ensure && cd ..

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
16 etapas, grava todos os artefatos, renderiza em 640x360 e nao faz uma unica
chamada externa.

### Rodar de verdade

A sessao do Claude Code grava `dossie.json`, `roteiro.pt-br.json` e
`relatorio_fatos.json` numa pasta (formato em `src/mundoantigo/session/schemas.py`):

```bash
uv run mundoantigo nova "<tema>" --roteiro-da-sessao data/sessao/<tema>
uv run mundoantigo painel      # http://127.0.0.1:8765
uv run mundoantigo worker      # noutro terminal; o ComfyUI precisa estar no ar
```

---

## Como funciona

Cada producao e um roteiro que vira **dois videos**. Pesquisa, checagem de
fatos e imagens servem aos dois idiomas; so a narracao e o texto na tela mudam.

```
sessao: pesquisa ─► roteiro + relatorio de fatos ─► importar
                                                     │
pauta ─► GATE ─► adaptacao EN ─► narracao ─► cenas ─► referencias ─► assets
                                     │                                    │
                                     └─► trilha                      pre-checagem
                                           │                              │
                                           │                    REVISAO DAS IMAGENS
                                           │                              │
          entrega ◄─ REVISAO FINAL ◄─ montagem ◄─ metadados ◄─────────────┘
```

As 16 etapas sao **idempotentes e retomaveis**: se algo falha, o pipeline
retoma da ultima etapa concluida sem repetir chamadas pagas. Ver
[ADR 0002](docs/decisoes/0002-fila-e-retomada.md). A narracao vem antes das
cenas, que sao cortadas pela duracao real de cada frase
([ADR 0008](docs/decisoes/0008-narracao-antes-das-cenas.md)); refazer a voz
nao refaz as imagens. A trilha anda enquanto as imagens esperam revisao.

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
uv run mundoantigo nova "<tema>" --roteiro-da-sessao <pasta>   # valida e enfileira
uv run mundoantigo importar-roteiro <id> <pasta> [--validar-apenas]
uv run mundoantigo worker                # executa as etapas da fila
uv run mundoantigo worker --ensaio       # ... com provedores falsos, custo zero
uv run mundoantigo status [<video_id>]   # estado da fila ou de uma producao
uv run mundoantigo custos                # gasto do mes por etapa e por producao
uv run mundoantigo aprovar <video_id> [--etapa revisao_imagens]   # portoes humanos
uv run mundoantigo rejeitar <id> "<motivo>"
uv run mundoantigo refazer <id> <etapa> [--apagar]
uv run mundoantigo livro <arquivo.pdf>   # ingere um livro e classifica os direitos
uv run mundoantigo painel                # sobe o painel web local
uv run mundoantigo backup                # espelha banco, videos e bibliotecas no D:
uv run mundoantigo estilo calibrar       # folhas de estilo lado a lado com o teste antigo
uv run mundoantigo personagem poses --figurino "<figurino>"
uv run mundoantigo voz identificar <video.mp4>
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
| **Producao** | As 16 etapas, o relatorio de fatos, os artefatos, refazer uma etapa |
| **Revisao** | Corte final: os dois videos, os metadados com avisos e as thumbs de um lado, o relatorio de fatos do outro. Aprovar ou rejeitar com motivo |
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
  providers/         llm, imagem, tts, alinhamento, busca, referencias — todos atras de adaptador
  pipeline/          maquina de estados, fila, gate de fatos, as 16 etapas
  session/           formato e importacao do roteiro feito na sessao
  references/        licencas e ranking das fotos do Commons
  publishing/        descricao, limites do YouTube e thumbnails
  style/             calibracao de estilo e poses do MC
  books/             ingestao, classificacao de direitos, base vetorial
  render/            ponte para o Remotion
  web/               painel FastAPI + templates
render/              projeto Remotion (Node/TS): 2.5D, camadas de texto, MC, baloes, cartoes
biblioteca/          poses do MC por figurino, trilhas, sfx
videos/<video_id>/   artefatos de cada producao, por etapa; entrega/ e o pacote final
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
uv run pytest              # ~370 testes, ~30 s, sem rede e sem GPU
uv run pytest -m slow      # + render de verdade no Remotion (exige npm ci)
uv run ruff check src tests
uv run mypy
```

O conjunto padrao cobre o pipeline de ponta a ponta com provedores falsos,
incluindo um video-exemplo de ~60 s, a retomada sem repetir chamadas pagas e o
contrato de props entre Python e Remotion.

---

## Estado do projeto

O trabalho feito depois de 10/09/2026 se perdeu numa falha de disco e foi
reconstruido em 29/09 a partir dos videos entregues (brief, secao 14).

Pronto:
- **Fase A:** ambiente e backup diario.
- **Fase B,** paridade com as entregas:
  - ComfyUI com Z-Image e estilo b-sombreado aprovado;
  - vozes do Kokoro identificadas;
  - importacao da sessao;
  - narracao frase a frase com SRT igual ao roteiro;
  - storyboard v2 com cenas de ~6 s;
  - camadas do Remotion (titulos, tarjas, baloes, MC recortado, cartoes);
  - fotos de referencia do Commons;
  - descricao, thumbnails e pacote de entrega.

Falta:
- **Fase B:** a rodada de paridade, com o video do legionario refeito em ~20 min.
- **Fase C, a esteira:**
  - pre-checagem das imagens;
  - grade de revisao;
  - notificacoes na barra de tarefas;
  - skill da sessao.
- **Fase D:** trilha e efeitos, so da YouTube Audio Library.
