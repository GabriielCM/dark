---
id: metadados/pacote
version: 3
modelo_sugerido: rapido
descricao: "Titulo, titulos alternativos, os dois paragrafos da descricao, tags e o texto da thumbnail. Capitulos, fontes, aviso e creditos sao montados por codigo. v3: titulos mais marcantes, no vocabulario de busca de cada idioma (dados do Studio de 05/10/2026)."
variaveis: [idioma, titulo_roteiro, capitulos, roteiro, thumbnail, feedback_revisor]
---
Escreva os metadados de publicação deste vídeo para o YouTube. Idioma de saída: **{idioma}**.

Se o idioma for inglês, escreva como um redator nativo escreveria, e não como tradução do português. Se for português, use a acentuação completa e correta: "não", "história", "também", "até".

## O vídeo

- Título de trabalho: {titulo_roteiro}
- Capítulos, na ordem: {capitulos}
- Conceito da thumbnail: {thumbnail}

## Roteiro narrado

{roteiro}

## Pedido do revisor

{feedback_revisor}

Se houver um pedido acima, ele tem prioridade sobre as regras abaixo.

## Como o canal é encontrado

Quase todo o público chega pelos vídeos sugeridos: o YouTube mostra o nosso vídeo ao lado de vídeos populares do mesmo tema, e isso acontece quando o título usa as mesmas palavras que eles. No canal PT, o vídeo cujo título repetia o de um vídeo grande do tema ("Como os Romanos faziam concreto que dura dois mil anos") recebeu 21 vezes mais impressões que um título descritivo ("Um dia na vida de um legionário romano em marcha").

O vocabulário muda de um idioma para o outro. "Como os romanos..." funciona em português; em inglês, os títulos fortes do mesmo tema podem ser outros ("How the Romans...", "A Day in the Life of a Roman Soldier"). Escreva para o público de **{idioma}**, não traduza.

## Regras

1. **Título:** até 70 caracteres, com as palavras principais nos primeiros 50.
   - **Comece pelo que o público digita** para buscar o tema nesse idioma, como os títulos dos vídeos mais vistos sobre ele.
   - **Seja marcante:** um gancho concreto que dê vontade de clicar, como um número surpreendente, um contraste, uma pergunta que o vídeo responde ou o fato mais inesperado do roteiro.
   - Todo número e todo fato do título têm de estar no roteiro, que passou pela checagem de fatos. Prometa exatamente o que o vídeo entrega.
   - O título de trabalho é só referência: não o copie.
   - Proibido: título descritivo de catálogo, "você não vai acreditar", promessa falsa, caixa alta gratuita e emoji.
   - Fraco: "Um dia na vida de um legionário romano em marcha". Forte: "Como os soldados romanos marchavam quase 30 km por dia".
2. **Títulos alternativos:** dois, com ângulos diferentes do principal e as mesmas regras, um pela pergunta e outro pelo fato mais surpreendente. Vão para o "Testar e comparar" do YouTube.
3. **Parágrafos:** exatamente dois, de 60 a 110 palavras cada, em tom documental sério.
   - O primeiro abre com a pergunta ou a tensão central do vídeo e repete as palavras de busca do título na primeira frase.
   - O segundo diz o que o espectador vai descobrir, citando pessoas, lugares e pesquisas que aparecem no roteiro.
   - Sem links, sem carimbos de tempo, sem hashtags e sem lista de fontes: capítulos, fontes e créditos são acrescentados depois, por código.
   - Nada que não esteja no roteiro. O roteiro passou pela checagem de fatos; a descrição não pode acrescentar afirmações.
4. **Tags:** de 12 a 15, da mais específica para a mais genérica, cada uma com até 30 caracteres, sem "#". Inclua os termos de busca do título e as variações comuns no idioma (por exemplo, "soldado romano" e "legionário romano").
5. **Texto da thumbnail:** até 4 palavras, que completem o título em vez de repeti-lo. Deve funcionar em caixa alta e ser lido num relance.

## Saída

JSON válido, sem cercas de código:

```
{{
  "titulo": "...",
  "titulos_alternativos": ["...", "..."],
  "paragrafos": ["...", "..."],
  "tags": ["..."],
  "thumbnail_texto": "..."
}}
```
