---
name: esteira
description: Conduz uma producao do canal Mundo Antigo pela esteira (fase C): a partir do tema escolhido, abre a pagina da producao no navegador do usuario, faz pesquisa e roteiro na sessao, vigia a pagina e atende os pedidos de refacao, as respostas e os comentarios do corte final. Use sempre que o usuario escolher um tema, pedir para continuar uma producao, ou quando chegar um pedido, resposta ou comentario pela pagina.
---

# A esteira de uma producao

O usuario acompanha **tudo pela pagina da producao no navegador** (painel em
http://127.0.0.1:8765/videos/<id>). Ele so revisa duas coisas: a grade de
imagens e o corte final, e responde as perguntas que voce faz **na pagina**. O
resto e com voce. Quando a producao precisa dele, o Windows avisa com som e o
clique abre a pagina direto na etapa.

Regras que nao mudam:

- **Nunca aprove no lugar do usuario** (`aprovar`, "Aprovar todas", corte final),
  a nao ser que ele peca isso explicitamente no chat.
- **Nunca rode worker, ComfyUI ou painel como tarefa em segundo plano da sessao**:
  ela morre em 2 h (foi assim que o ComfyUI caiu no video de Gize). Use sempre
  `uv run mundoantigo esteira`, que sobe tudo como processo destacado.
- Duvida ou sugestao para o usuario vai para a pagina (`perguntar`), nao so para o chat.
- Revisao de imagens e do corte e na pagina, nunca so no chat nem em folhas JPG.
  (As folhas de `imagens folhas` sao so a sua pre-checagem; o usuario revisa na grade.)

## 1. Tema escolhido

1. Enfileire **logo**, antes de pesquisar (a pagina passa a existir e mostra a
   pesquisa como "Com o Claude"):
   `uv run mundoantigo nova "<tema>" --pilar <pilar>`
   O comando imprime o `video_id`, sobe a esteira e abre a pagina no navegador.
2. Faca a pesquisa e o roteiro na sessao em `data/sessao/<slug>/` (formato em
   `src/mundoantigo/session/schemas.py`): `dossie.json`, `roteiro.pt-br.json` e
   `relatorio_fatos.json`. Inclua no roteiro:
   - `figurino` do MC, em ingles;
   - **`ambientacao`**, em ingles: epoca, lugar, o que as pessoas vestem e do que
     as construcoes sao feitas. Ela entra no prompt de toda imagem de gente e
     lugar. Sem ela, pessoas e cidades saem modernas ou europeias. **So o
     cenario, nunca o assunto do video:** nos aquedutos, "aqueduct arches, lead
     pipes" na ambientacao poe arcos e canos em quase toda imagem.

   No dossie, o `titulo` de cada fonte e o veiculo e o titulo **como publicados,
   no idioma da fonte** ("Wikipedia, Khufu", "University of Amsterdam, ..."), sem
   anotacoes da sessao. O ano vai em `ano`. O mesmo titulo vai para as descricoes
   PT e EN.
3. Mostre o andamento na pagina:
   `uv run mundoantigo nota <id> --etapa pesquisa "Dossie com 41 afirmacoes e 18 fontes"`
4. Valide e importe:
   `uv run mundoantigo importar-roteiro <id> data/sessao/<slug>`
   O worker segue sozinho: adaptacao EN, narracao, storyboard, referencias e imagens.

## 2. Vigia

Enquanto a producao estiver aberta, deixe um vigia em segundo plano e rearme
sempre que ele acordar:

    uv run mundoantigo aguardar <id> --timeout 6000

Ele acorda quando o usuario responde uma pergunta, envia pedidos de refacao com
motivo ou envia comentarios do corte final (saida 0), ou quando o tempo acaba
(saida 3: so rearme). Enquanto roda, a pagina mostra "o Claude esta acompanhando".

## 3. Pre-checagem das imagens

Quando a etapa de imagens termina, a grade fica parada esperando o usuario.
Antes de ele revisar, confira voce as imagens (a pre-checagem automatica ainda
nao existe). Com cenas de ~3 s sao 350 a 400 imagens por video (ADR 0012):
confira pelas folhas de 12 miniaturas, capitulo a capitulo, e abra o PNG em
`videos/<id>/assets/` so das suspeitas.

    uv run mundoantigo imagens folhas <id> [--capitulo N]   # imprime os caminhos; leia com Read
    uv run mundoantigo imagens folhas <id> --chaves cena-045,cena-072-peca-1   # so as refeitas

Procure gente ou lugar moderno, texto errado ou ilegivel dentro da imagem (texto
certo pode ficar desde 10/10, com o video so em PT), objeto errado, cara de
foto, e duas cenas seguidas da mesma frase com a mesma imagem (a cena que
continua a frase deveria ser outro plano do mesmo momento).

Para refazer uma imagem errada sem esperar o usuario:

    uv run mundoantigo imagens descrever <id> cena-045 "<descricao nova em ingles>" --resposta "o que mudou"
    uv run mundoantigo imagens aplicar <id>

Descricao boa: forma, material e uso do objeto; **nunca negacao** ("no crosses"
desenha cruzes); pessoas e lugares com a epoca. Para trocar so a semente:
`imagens refazer <id> <chave>`.

## 4. Pedidos de refacao do usuario

- Com **link**: o worker aplica sozinho (Commons tem a licenca conferida; outro
  site entra como "licenca nao verificada").
- Com **motivo**: e com voce.
  1. `uv run mundoantigo imagens pedidos <id> --json` lista o pedido, o motivo, a
     narracao, a descricao atual e o caminho da imagem.
  2. Leia a imagem (Read no `imagem_absoluta`) e escreva a descricao nova.
  3. `imagens descrever <id> <chave> "<nova>" --pedido <n> --resposta "<o que mudou>"`
     (a resposta aparece para o usuario no cartao).
  4. `uv run mundoantigo imagens aplicar <id>`.
  Se nao for refazer: `imagens recusar <id> <pedido> "<por que>"`.

O worker gera so as imagens pedidas (semente nova a cada refacao) e a grade
volta a esperar o usuario, com aviso.

## 5. Corte final

Depois da aprovacao da grade, o worker faz metadados, montagem e os cortes do
TikTok (ADR 0010) e avisa o usuario. Ele comenta momentos do video, ou de um
corte, na pagina. Quando o vigia acordar:

    uv run mundoantigo corte comentarios <id> --json

Um comentario com `corte` e de um corte do TikTok, e o tempo e o do corte.
Para cada comentario, decida:

- **imagem** → `imagens descrever` + `imagens aplicar` (refaz so a imagem, a montagem, os cortes e os metadados);
- **texto ou fato** → corrija o roteiro na sessao e `importar-roteiro <id> <pasta> --motivo "..."`;
- **voz** → `refazer <id> narracao`;
- **metadados** → `refazer <id> metadados`;
- **corte do TikTok** (trecho fraco, gancho, legenda) → `cortes listar <id> --candidatos` e
  `cortes editar <id> <n> --candidato c07` ou `--gancho-pt "..."`/`--legenda-en "..."`.
  Nao chama o LLM e re-renderiza so o que mudou. O gancho sai do proprio trecho:
  nada que nao esteja nele (gate de fatos). Cada corte e de uma conta so (`listar`
  mostra o idioma): o texto vai no idioma dele, e um trecho novo nao pode
  repetir o de outro corte, nem da outra conta. Desde 08/10/2026 a conta EN
  esta parada e a PT posta 6 cortes (`tiktok.cortes` em `config/canais/`): nas
  producoes novas, todo corte e PT.

Depois responda: `uv run mundoantigo corte resolver <id> <n> "<o que foi feito>"`
(ou `--descartar` com o porque). O usuario aprova pela pagina.

## 6. Perguntar ao usuario

    uv run mundoantigo perguntar <id> "Prefere a versao A ou B da cena 45?" --opcao A --opcao B --alvo cena-045

A pergunta aparece no topo da pagina e o Windows avisa com som. A resposta chega
pelo vigia, ou espere so ela: `uv run mundoantigo respostas <id> --pergunta <n> --esperar`.

## Diagnostico

- `uv run mundoantigo esteira --status` (o que esta rodando) e `esteira <id>` (sobe o que faltar e abre a pagina).
- `uv run mundoantigo status <id>`; logs em `data/logs/{worker,painel,comfyui}.log`.
- `uv run mundoantigo notificar <id>` mostra um aviso de teste (som e clique).
- Etapa travada: botao "Tentar de novo" na pagina, ou `refazer <id> <etapa>`.
