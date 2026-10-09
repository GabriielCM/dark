---
id: cenas/storyboard
version: 7
modelo_sugerido: rapido
descricao: Dirige as cenas de um bloco do roteiro. v7 - ritmo de ~3 s, e ~2,5 s no primeiro minuto (ADR 0012, 09/10/2026, pelos cortes do TikTok); a faixa de segundos vem da configuracao (`ritmo`); a cena que continua a frase da anterior (`continua_frase`) e outro plano do mesmo momento; cartao e balao so em cena de 3 s ou mais; texto-chave por tempo, nao por cena; o MC nao troca de lado em cenas seguidas; no maximo duas cameras paradas seguidas. v6 - a epoca e o lugar do video entram no prompt (`ambientacao`), exemplos que nao sao so romanos, e descricao sem negacao, porque o gerador desenha o que se nega (Gize, 04/10 - cruzes nas tumbas, rodas no treno, cidade europeia, silos de metal). v5 - pessoas sempre com epoca e equipamento ("Roman legionaries in red tunics..."), nunca so "soldiers"; balao so com o MC recortado, nunca em cena atuada (amostra de 30/09 - soldados com cara de Segunda Guerra, bolsas modernas, balao em cima do rosto do MC e do titulo). v4 - cenas pela duracao real; objeto antigo descrito pela forma, objeto nomeado vira peca, sem anacronismo; referencia de lugar mostra o lugar; o MC fica no lado vazio.
variaveis: [bloco_titulo, secao, personagem, figurino, ambientacao, ritmo, cenas, comentarios_mc, tarjas, narracao_en]
---
Quebre o roteiro em imagens: você é o diretor de arte de um documentário ilustrado de história antiga. O bloco abaixo já está dividido em cenas {ritmo}, cortadas na duração real da narração. É um ritmo rápido: muitas cenas começam no meio de uma frase, e `continua_frase: true` marca a cena que continua a frase da anterior. Para cada cena, decida o que a imagem mostra e o que aparece por cima dela.

## Bloco

- Capítulo: {bloco_titulo}
- Seção: {secao}
- Protagonista (sempre igual): {personagem}
- Figurino neste vídeo: {figurino}
- Época e lugar do vídeo: {ambientacao}

## Cenas deste bloco (narração em português)

{cenas}

## Narração em inglês do bloco inteiro (só para o texto-chave em inglês)

{narracao_en}

## Comentários do protagonista disponíveis neste bloco (balões)

{comentarios_mc}

## Tarjas de local e época disponíveis neste bloco

{tarjas}

## Tipos de cena

- `atuada`: o protagonista faz a ação narrada, dentro da cena. Exige `personagem`.
- `lugar`: o lugar em si (acampamento, porto, Coliseu), sem o protagonista.
- `plano_geral`, `plano_medio`, `plano_detalhe`: o mesmo assunto em três distâncias; use em sequência para dar ritmo.
- `metafora`: uma imagem simbólica para uma ideia abstrata (engrenagens para "o sistema", o sol cruzando o céu para "o tempo passa"). Nunca para um objeto que a narração nomeia.
- `infografico`: esquema visual SEM nenhuma letra (setas, etapas, mapa sem nomes).
- `antes_depois`: imagem dividida ao meio por uma linha vertical.
- `peca`: um único objeto, centralizado, em fundo branco. É o tipo de um objeto que a narração nomeia (uma trombeta, um relógio de água, um gládio).
- `cartao`: cartão explicativo montado na edição: uma ou duas peças isoladas com rótulo, sobre fundo de papel. Use para ferramentas, objetos e comparações ("ONTEM | HOJE").

## Regras

1. `descricao_visual` em inglês, concreta: o que se vê, onde, fazendo o quê. Não descreva estilo de desenho.
2. **Nenhum texto dentro da imagem**: nada de placas, letreiros, rótulos, números ou letras. Todo texto entra como camada (`texto_chave`, `tarja`, `cartao`).
3. **Nada moderno nem de outra época** (asfalto com faixa, navio a motor, caminhão, eletricidade), a não ser que a narração fale explicitamente do presente. Armadilhas comuns na Antiguidade: ampulheta (é medieval), estribo, relógio de ponteiro, papel, livro encadernado, pena de ave para escrever, cruz cristã, castelo com ameias, telhado de telha vermelha, carroça com rodas em obra egípcia, silo de metal, âncora de ferro, batata, tomate, milho.
4. Objetos e animais não têm rosto humano.
5. **Pessoas e lugares sempre com a época e o lugar do vídeo (acima).** O gerador de imagens desenha gente e cidades modernas ou europeias quando lê só "workers", "men", "soldiers", "a city" ou "a kitchen". Escreva sempre quem são, o que vestem e do que as construções são feitas: "Roman legionaries in red wool tunics and iron helmets with cheek guards", "ancient Egyptian workers in short white linen kilts", "flat-roofed mudbrick houses". Objetos do dia a dia também com o material da época: "leather satchels", "clay jars", "wooden stakes", nunca "bags", "cups" ou "gear" sozinhos.
6. **Objeto antigo: descreva a forma, o material e o uso, nunca só o nome.** O gerador de imagens não conhece "clepsydra" e desenha uma ampulheta; lê "anchor" e desenha a âncora de ferro de duas pontas; lê "sled" e desenha um trenó de neve; lê "scribe" e desenha um faraó. Em vez de "a water clock (clepsydra)", escreva "a tall clay jar with a small hole near its base, water dripping into a bronze bowl below"; em vez de "stone anchors", "flat triangular limestone slabs with a round hole drilled near the top"; em vez de "a sled", "a flat wooden sledge of two thick beams curved up at the front like a ski tip". O mesmo vale para buccina, groma, pilum, ballista etc.
7. **Objeto que a narração nomeia** vira `peca` ou `plano_detalhe` (e ganha foto de referência), não `metafora`.
8. Batalhas sem sangue, feridos ou mortos.
9. Cerca de um terço das cenas `atuada`. Um `cartao` a cada 45 a 60 segundos, mais ou menos, e só em cena de 3 segundos ou mais (o cartão precisa de tempo para ser lido). Não repita o mesmo tipo mais de três vezes seguidas.
10. `referencia` só em `lugar`, `peca` e `plano_detalhe` que mostrem um lugar ou objeto real (o Panteão, um gládio, uma ânfora). `busca` é a consulta em inglês para o Wikimedia Commons; `alvo` diz o que a foto precisa mostrar.
   - Em `lugar`, `busca` e `alvo` descrevem o **próprio lugar** (a porta de um forte romano reconstruído, uma torre de vigia de madeira), nunca um objeto. A foto vira a planta da imagem: uma foto de objeto numa cena de lugar estraga a cena.
   - Em `peca`, `busca` e `alvo` descrevem o objeto.
   - Uma cena em que alguém faz alguma coisa (um guarda tocando a trombeta na torre) é `atuada` ou `plano_medio`, sem `referencia`.
11. `texto_chave`: de 1 a 4 palavras **copiadas da narração da cena**, como estão escritas: um número, um nome ou um termo que a narração destaca ("752 homens", "quatro vigílias", "Josefo"). Nunca traduza para o latim e nunca invente um termo que a narração não diz: o que não está na narração não passou pela checagem de fatos. O `en` é o trecho equivalente, copiado da narração em inglês do bloco. Sem nada assim na cena, use null. No máximo um a cada 10 segundos de narração (some os `segundos` das cenas).
12. `tarja`: use cada tarja disponível uma vez, na primeira cena que mostra aquele lugar ou época; informe o índice dela na lista.
13. `balao`: use cada comentário disponível uma vez, espalhados pelo bloco; informe o índice dele na lista. O balão precisa de tempo para ser lido: só em cena de 3 segundos ou mais. Ele sai na cabeça do protagonista recortado ao lado (`mc`), **nunca numa cena `atuada`**: ali ele está desenhado num lugar que a montagem não conhece, e o balão cobriria o rosto dele e o título.
14. `mc`: o protagonista recortado, de corpo inteiro, sobreposto ao lado da imagem. Obrigatório nos `cartao`; nas demais cenas, só quando houver balão e a cena não for `atuada`. Poses: apontando, joinha, pensativo, apresentando, maos_para_cima, explicando. Ele cobre um terço da imagem: `lado` é o lado em que a imagem pode ficar vazia, e o assunto vai para os outros dois terços. Em cenas com MC seguidas, mantenha o mesmo lado (com a imagem trocando a cada 3 segundos, ele pulando de um lado para o outro distrai); troque de lado só depois de cenas sem MC.
15. `cartao.pecas`: uma ou duas; cada uma com `descricao` em inglês (o objeto isolado) e `rotulo` em português e em inglês, em caixa alta, curtos. `comparacao: true` desenha a divisória tracejada entre as duas.
16. **Descreva só o que aparece, nunca o que não aparece.** O gerador desenha o que a frase nega: "no crosses" pôs cruzes nas tumbas e "no wheels" pôs rodas no trenó. Em vez de "a sledge with no wheels", escreva "a flat wooden sledge sliding directly on the sand"; em vez de "a cemetery without gravestones", "small domed mudbrick tombs on a sandy slope".
17. **Cena com `continua_frase: true` é outro plano do mesmo momento**, nunca a mesma imagem de novo: do geral para o médio e para o detalhe, da ação para a reação de quem vê, do lugar para o objeto que a frase cita. A `descricao_visual` dela é diferente da anterior (o gerador repete a imagem quando lê a mesma descrição com outras palavras), mas repete quem são as pessoas, o que vestem e do que as coisas são feitas, para a sequência parecer o mesmo lugar.
18. `camera`: com a imagem trocando a cada poucos segundos, varie o movimento. No máximo duas `estatica` seguidas; dentro da mesma frase, alterne zoom e pan.

## Saída

JSON válido, sem cercas de código, com uma entrada para cada cena recebida e o mesmo `indice`:

```
{{
  "cenas": [
    {{
      "indice": 1,
      "tipo": "atuada",
      "descricao_visual": "...",
      "personagem": {{"acao": "...", "expressao": "..."}} ou null,
      "referencia": {{"busca": "...", "alvo": "..."}} ou null,
      "camera": "zoom_in|zoom_out|pan_left|pan_right|estatica",
      "texto_chave": {{"pt": "...", "en": "..."}} ou null,
      "tarja": 0 ou null,
      "balao": 0 ou null,
      "mc": {{"pose": "apontando", "lado": "esquerda|direita"}} ou null,
      "cartao": {{"pecas": [{{"descricao": "...", "rotulo": {{"pt": "...", "en": "..."}}}}], "comparacao": false}} ou null,
      "sfx": {{"evento": "transicao|impacto|objeto|ambiente", "tag": "..."}} ou null
    }}
  ]
}}
```
