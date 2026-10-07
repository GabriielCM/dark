---
id: adaptacao/encurtar
version: 1
modelo_sugerido: principal
descricao: "Encurta so os blocos da adaptacao EN que passaram do limite de palavras, sem perder fato (ADR 0011)."
variaveis: [blocos, unidades, tom]
---
These blocks of an English documentary narration are too long. Each one has to fit in the time its Portuguese original takes, because both narrations play over the same video. Rewrite only the `narracao` of each block so it stays **at or under its word limit**.

## Blocks

Each item has the Portuguese original (`pt`, approved and fact-checked), the current English adaptation (`en`) and the word limit (`limite_palavras`):

{blocos}

## Rules

1. **Keep every fact.** Same claims, numbers, names, dates, attributions and hedges as the Portuguese. "We don't know" stays "we don't know". Never upgrade a hypothesis to a fact.
2. **Keep the beats in the same order.** The images follow the narration, so each idea has to stay where it is. Shorten each sentence; do not move or merge ideas across the block.
3. **Cut padding, not content:** filler phrases, doubled adjectives, restatements, "as we will see".
4. **Same voice:** {tom}; second person if the original speaks to the viewer; units as {unidades}.
5. Write natural English, not compressed telegraph style.

## Output

Valid JSON, no code fences, with one item per block received:

```
{{
  "blocos": [
    {{"indice": 0, "narracao": "...", "palavras": 0}}
  ]
}}
```
