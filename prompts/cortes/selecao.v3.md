---
id: cortes/selecao
version: 3
modelo_sugerido: rapido
descricao: "Escolhe os trechos que viram cortes verticais no TikTok, separados por conta, sem repetir trecho, e escreve no idioma de cada conta o gancho na tela, a legenda do post e as hashtags. Os candidatos chegam medidos por codigo; o modelo so escolhe e escreve (ADR 0010). v3: a quantidade de cada conta vem do canal (`tiktok.cortes`), e uma conta pode estar parada, como a EN desde 08/10/2026."
variaveis: [contas, titulo_pt, titulo_en, candidatos, gancho_max_palavras, hashtag_pt, hashtag_en, hashtags_min, hashtags_max, feedback_revisor, video_inteiro]
---
Escolha os cortes deste vídeo para o TikTok e escreva os textos de cada um.

## O vídeo

Documentário narrado de história antiga, de cerca de 20 minutos, em segunda pessoa e no presente. O mesmo vídeo sai em dois idiomas:
- PT, "Mundo Antigo": {titulo_pt}
- EN, "How the Ancient World Worked": {titulo_en}

## As contas

Cada conta do TikTok posta os próprios cortes, no idioma dela. Quantos cortes cada uma posta neste vídeo:

{contas}

{video_inteiro}

## Como o TikTok mede um corte

- Uma view só conta depois de 5 segundos assistidos. Quem não se prende nos primeiros segundos vai embora.
- O pagamento pesa o tempo assistido e quantos assistem até o fim. Um corte que perde o fio no meio rende menos.
- A busca do TikTok lê a legenda do post, o texto na tela e a fala.

## Os candidatos

Os trechos abaixo já cabem na duração do corte. Cada um traz o texto narrado no idioma de cada conta que posta.

{candidatos}

## Pedido do revisor

{feedback_revisor}

Se houver um pedido acima, ele tem prioridade sobre as regras abaixo.

## Regras

1. **Escolha para cada conta a quantidade pedida em "As contas".** Um candidato vai para uma conta só, e nenhum corte pode se sobrepor a outro no tempo, nem entre as contas. Prefira blocos diferentes e assuntos diferentes, espalhados pelo vídeo. Prefira o trecho que:
   - começa forte: a primeira frase prende sozinha, sem depender do que veio antes. Evite começar com "isso", "ele", "por isso" ou qualquer referência a algo que o espectador não viu;
   - se sustenta sozinho: quem nunca viu o vídeo entende do começo ao fim;
   - entrega um fato concreto e surpreendente, um número, uma descoberta, um contraste;
   - termina fechando a ideia, e não no meio de um raciocínio.
2. **Gancho na tela**, só no idioma da conta: até {gancho_max_palavras} palavras, que aparecem no alto da tela nos 3 primeiros segundos, sem narração.
   - Tire o gancho do próprio trecho: o fato mais surpreendente dele, ou a pergunta que ele responde. O roteiro passou pela checagem de fatos; o gancho não pode afirmar nada que não esteja no trecho.
   - Proibido: "você não vai acreditar", promessa que o trecho não cumpre, emoji, hashtag e caixa alta (a tela cuida do estilo).
   - Fraco: "Curiosidades sobre as pirâmides". Forte: "Onze bois por dia para quem erguia a pirâmide".
3. **Legenda do post**, só no idioma da conta, de 150 a 300 caracteres:
   - A primeira linha, com até 70 caracteres, é a frase que as pessoas digitariam para buscar esse assunto nesse idioma ("Como os egípcios alimentavam quem construiu as pirâmides").
   - Depois, uma ou duas frases de contexto, só com o que está no trecho.
   - Termine com uma pergunta que puxe comentário.
   - Sem hashtags, sem links e sem "vídeo completo": o código acrescenta essa linha e as hashtags.
4. **Hashtags**, no idioma da conta: de {hashtags_min} a {hashtags_max} no total, contando a fixa do canal ({hashtag_pt} no PT, {hashtag_en} no EN), que entra sozinha. Escreva as outras: uma ou duas amplas (#historia, #history) e uma ou duas do assunto (#egitoantigo, #ancientegypt). Minúsculas, sem acento e sem espaço.
5. **Vídeo inteiro:** a legenda do post do vídeo completo, com as mesmas regras da legenda dos cortes. A primeira linha é a busca pelo assunto do vídeo todo, e o texto diz que é o documentário completo, de cerca de 20 minutos. Mais as hashtags dele.
6. **Inglês:** escreva como um redator nativo escreveria, a partir do texto EN do trecho, e não como tradução do português. **Português:** acentuação completa e correta.

## Saída

JSON válido, sem cercas de código. Em cada corte, `conta` é "pt" ou "en", sempre de uma conta que posta, e os textos ficam no idioma dessa conta. Os cortes podem vir em qualquer ordem: o código os põe na ordem do vídeo.

```
{{
  "cortes": [
    {{"candidato": "c07", "conta": "pt", "gancho": "...", "legenda": "...", "hashtags": ["#...", "#..."]}},
    {{"candidato": "c12", "conta": "pt", "gancho": "...", "legenda": "...", "hashtags": ["#...", "#..."]}}
  ],
  "video_inteiro": {{
    "legenda": {{"pt": "..."}},
    "hashtags": {{"pt": ["#..."]}}
  }}
}}
```
