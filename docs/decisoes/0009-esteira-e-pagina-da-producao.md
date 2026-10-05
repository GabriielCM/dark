# ADR 0009: A esteira e a página da produção

- **Status:** aceito
- **Data:** 05/10/2026
- **Depende de:** [ADR 0001](0001-stack.md), [ADR 0002](0002-fila-e-retomada.md), [ADR 0006](0006-referencias-commons.md)

## Contexto

No alinhamento de 09/2026, o usuário pediu para acompanhar cada produção por uma página no navegador, a partir do momento em que escolhe o tema:

- uma lista das etapas;
- um aviso do Windows com som quando a produção trava em algo que precisa dele;
- a grade de imagens na própria página, com refazer por imagem (link de referência ou motivo);
- o mesmo esquema no corte final;
- as dúvidas do Claude também na página.

A primeira produção completa (Gizé, 04/10) foi feita sem isso. A grade foi para folhas JPG no chat, e o ComfyUI, rodando como tarefa em segundo plano da sessão do Claude, caiu ao bater no limite de 2 h.

## Decisão

**A página da produção é o lugar do revisor.** `/videos/<id>` mostra as 16 etapas como uma lista que expande ao clicar (`<details>`). O cabeçalho de cada etapa traz estado, resumo, progresso e tempo, e se atualiza a cada 4 s por uma API JSON. O JavaScript atualiza só os cabeçalhos e os cartões, nunca o formulário que o revisor está preenchendo. `?abrir=<etapa>` abre a etapa e rola até ela; é o link que o aviso usa.

**A grade de imagens fica dentro da etapa `revisao_imagens`.** Ela traz a thumbnail e as poses do MC no topo, depois uma seção por capítulo. Cada cartão tem a caixa "Refazer", com um campo de link e um de motivo, e salva sozinho.

- Pedido só com link: o worker aplica entre etapas (`Runner.maintain`). Ele baixa a foto (licença conferida se for do Commons), arquiva a imagem antiga, conta a refação no storyboard e devolve só aquela imagem para a fila (`Runner.redo_images`).
- Pedido com motivo: vai para a sessão do Claude, que lê a imagem e reescreve a descrição (`mundoantigo imagens descrever` e `aplicar`).
- A semente só muda quando há refação: imagem aprovada nunca sai diferente por acaso.

**O corte final fica na etapa `revisao`.** O revisor clica em "Comentar neste momento" no player. O tempo vira a cena daquele instante, pelos tempos de `montagem/props.<idioma>.json`, que são diferentes em PT e EN. Os comentários enviados vão para a sessão, que decide o que refazer e responde cada um. Aprovar exige que nenhum comentário esteja aberto.

**Estado das revisões em JSON por vídeo**, com trava e troca atômica (`artifacts/jsonfile.py`): `revisao_imagens/pedidos.json`, `revisao/comentarios.json` e `conversa/perguntas.json`. Painel, worker e CLI escrevem neles. O que vira aviso fica numa tabela `events`.

**Avisos atrás de um adaptador** (`notify/`, `notificacoes.padrao`: windows, log ou nenhum).

- No Windows, o aviso é um toast com som (Reminder) que fica na tela até ser fechado. O clique e o botão abrem a página por ativação por protocolo, que o próprio Windows resolve.
- Viram aviso: etapa que espera o revisor, falha definitiva, teto de orçamento, pergunta do Claude e pacote pronto (este é discreto).
- A espera da sessão do Claude (pesquisa e roteiro) é só registro.
- O mesmo aviso não se repete em 10 minutos.

**A esteira sobe destacada.** `mundoantigo esteira [<id>]`, chamado também pelo `nova`, sobe o que falta: ComfyUI (quando o provedor de imagem é o comfyui local), painel e worker.

- São processos destacados, fora do job de quem chamou, com pid em `data/run/` e log em `data/logs/`.
- Depois abre a página na etapa que precisa do revisor.
- É idempotente: chamar de novo só confere e abre a página.

**A sessão do Claude conversa pela CLI.**

- `perguntar` põe a pergunta no topo da página, com aviso.
- `aguardar` fica de vigia em segundo plano: acorda com uma resposta, um pedido com motivo ou um comentário do corte, e grava um sinal de presença que a página mostra.
- `imagens …`, `corte …` e `nota` completam o conjunto.
- O fluxo está na skill `.claude/skills/esteira/SKILL.md`.

## Alternativas consideradas

- **Estado das revisões no banco.** Daria concorrência de graça, mas espalharia o estado de um vídeo entre dois lugares e esconderia da sessão o que ela precisa ler. Os arquivos são legíveis, entram no backup e a trava tem 40 linhas.
- **O painel aplicar os pedidos com link na hora.** A resposta viria em segundos, mas o painel passaria a escrever o storyboard enquanto o worker pode estar gerando imagens. Um painel reiniciado no meio deixaria pedidos presos. O worker já é quem gera, e aplicar entre etapas não disputa com ninguém.
- **Server-sent events ou WebSocket na página.** Seriam mais imediatos, mas um polling de 4 s basta para uma pessoa revisando, e não precisa de nada novo no servidor.
- **O worker chamar o Claude sozinho (`claude -p`) para os pedidos com motivo.** Teria mais peças, consumiria o plano do usuário e tiraria o Claude da conversa. O usuário preferiu a sessão de vigia, com a página dizendo quando ninguém está acompanhando.
- **Script PowerShell para a esteira.** O ADR 0005 previa um `scripts/esteira.ps1`. Python é testável e lê a configuração do `app.yaml`.

## Consequências

- O revisor nunca precisa do chat para revisar; o chat fica para o que é complicado.
- Uma imagem errada no corte final refaz só aquela imagem, os metadados (sem gastar LLM de novo) e a montagem, nunca as 222.
- A pré-checagem automática (CLIP, OCR, sonda de anacronismo) continua por fazer. Até lá, a sessão confere as imagens antes do revisor.
- **Reavaliar** se o painel for exposto fora da rede local (HTTPS e autenticação, CLAUDE.md), ou se o "processo destacado" morrer junto com a sessão em alguma máquina. A alternativa nesse caso é uma tarefa agendada do Windows, como em `scripts/registrar-tarefas.ps1`.
