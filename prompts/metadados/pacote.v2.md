---
id: metadados/pacote
version: 2
modelo_sugerido: rapido
descricao: "Titulo, titulos alternativos, os dois paragrafos da descricao, tags e o texto da thumbnail. Capitulos, fontes, aviso e creditos sao montados por codigo."
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

## Regras

1. **Título:** até 70 caracteres. Concreto e específico, prometendo exatamente o que o vídeo entrega. Sem clickbait, sem "você não vai acreditar", sem caixa alta gratuita, sem emoji.
2. **Títulos alternativos:** dois, com ângulos diferentes do principal (um pela pergunta, outro pela revelação). Vão para o "Testar e comparar" do YouTube.
3. **Parágrafos:** exatamente dois, de 60 a 110 palavras cada, em tom documental sério.
   - O primeiro abre com a pergunta ou a tensão central do vídeo.
   - O segundo diz o que o espectador vai descobrir, citando pessoas, lugares e pesquisas que aparecem no roteiro.
   - Sem links, sem carimbos de tempo, sem hashtags e sem lista de fontes: capítulos, fontes e créditos são acrescentados depois, por código.
   - Nada que não esteja no roteiro. O roteiro passou pela checagem de fatos; a descrição não pode acrescentar afirmações.
4. **Tags:** de 12 a 15, da mais específica para a mais genérica, cada uma com até 30 caracteres, sem "#".
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
