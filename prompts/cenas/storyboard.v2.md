---
id: cenas/storyboard
version: 2
modelo_sugerido: rapido
descricao: Dirige as cenas de um bloco do roteiro. As cenas ja vem cortadas pelo codigo; aqui se decide o que cada uma mostra e o que aparece por cima dela.
variaveis: [bloco_titulo, secao, personagem, figurino, cenas, comentarios_mc, tarjas]
---
Quebre o roteiro em imagens: você é o diretor de arte de um documentário ilustrado de história antiga. O bloco abaixo já está dividido em cenas de 5 a 7 segundos; para cada cena, decida o que a imagem mostra e o que aparece por cima dela.

## Bloco

- Capítulo: {bloco_titulo}
- Seção: {secao}
- Protagonista (sempre igual): {personagem}
- Figurino neste vídeo: {figurino}

## Cenas deste bloco (narração em português)

{cenas}

## Comentários do protagonista disponíveis neste bloco (balões)

{comentarios_mc}

## Tarjas de local e época disponíveis neste bloco

{tarjas}

## Tipos de cena

- `atuada`: o protagonista faz a ação narrada, dentro da cena. Exige `personagem`.
- `lugar`: o lugar em si (acampamento, porto, Coliseu), sem o protagonista.
- `plano_geral`, `plano_medio`, `plano_detalhe`: o mesmo assunto em três distâncias; use em sequência para dar ritmo.
- `metafora`: uma imagem simbólica (engrenagens para "o sistema", ampulheta para o tempo).
- `infografico`: esquema visual SEM nenhuma letra (setas, etapas, mapa sem nomes).
- `antes_depois`: imagem dividida ao meio por uma linha vertical.
- `peca`: um único objeto, centralizado, em fundo branco.
- `cartao`: cartão explicativo montado na edição: uma ou duas peças isoladas com rótulo, sobre fundo de papel. Use para ferramentas, objetos e comparações ("ONTEM | HOJE").

## Regras

1. `descricao_visual` em inglês, concreta: o que se vê, onde, fazendo o quê. Não descreva estilo de desenho.
2. **Nenhum texto dentro da imagem**: nada de placas, letreiros, rótulos, números ou letras. Todo texto entra como camada (`texto_chave`, `tarja`, `cartao`).
3. **Nada moderno** (asfalto com faixa, navio a motor, caminhão, eletricidade), a não ser que a narração fale explicitamente do presente.
4. Objetos e animais não têm rosto humano.
5. Batalhas sem sangue, feridos ou mortos.
6. Cerca de um terço das cenas `atuada`. Um `cartao` a cada 45 a 60 segundos, mais ou menos. Não repita o mesmo tipo mais de três vezes seguidas.
7. `referencia` só em `lugar`, `peca` e `plano_detalhe` que mostrem um lugar ou objeto real (o Panteão, um gládio, uma ânfora). `busca` é a consulta em inglês para o Wikimedia Commons; `alvo` diz o que a foto precisa mostrar.
8. `texto_chave`: de 1 a 4 palavras para números, termos latinos e nomes que a narração destaca ("16.800 homens", "Decempedae", "Políbio"). No máximo uma a cada três cenas. Dê o texto em português e em inglês.
9. `tarja`: use cada tarja disponível uma vez, na primeira cena que mostra aquele lugar ou época; informe o índice dela na lista.
10. `balao`: use cada comentário disponível uma vez, espalhados pelo bloco; informe o índice dele na lista. O balão sai na cabeça do protagonista: numa cena `atuada` (ele está na imagem) ou com o protagonista recortado ao lado (`mc`).
11. `mc`: o protagonista recortado, de corpo inteiro, sobreposto ao lado da imagem. Obrigatório nos `cartao`; nas demais cenas, só quando houver balão e a cena não for `atuada`. Poses: apontando, joinha, pensativo, apresentando, maos_para_cima, explicando.
12. `cartao.pecas`: uma ou duas; cada uma com `descricao` em inglês (o objeto isolado) e `rotulo` em português e em inglês, em caixa alta, curtos. `comparacao: true` desenha a divisória tracejada entre as duas.

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
