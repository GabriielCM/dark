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
     lugar. Sem ela, pessoas e cidades saem modernas ou europeias.
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
nao existe): olhe as miniaturas em `videos/<id>/assets/`, procure gente ou
lugar moderno, texto dentro da imagem, objeto errado, cara de foto.

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

Depois da aprovacao da grade, o worker faz metadados e montagem e avisa o
usuario. Ele comenta momentos do video na pagina. Quando o vigia acordar:

    uv run mundoantigo corte comentarios <id> --json

Para cada comentario, decida:

- **imagem** → `imagens descrever` + `imagens aplicar` (refaz so a imagem, a montagem e os metadados);
- **texto ou fato** → corrija o roteiro na sessao e `importar-roteiro <id> <pasta> --motivo "..."`;
- **voz** → `refazer <id> narracao`;
- **metadados** → `refazer <id> metadados`.

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
