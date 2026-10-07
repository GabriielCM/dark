---
id: adaptacao/en
version: 3
modelo_sugerido: principal
descricao: "Adapta (nao traduz) o roteiro PT-BR aprovado para o ingles, incluindo o que aparece na tela. v3: limite de palavras por bloco, para a narracao EN caber no tempo da PT (ADR 0011)."
variaveis: [roteiro_ptbr, ppm, duracao_alvo_min, duracao_alvo_max, unidades, tom, limites_por_bloco]
---
Adapt this Brazilian Portuguese documentary script for an English-language audience. This is an **adaptation, not a translation**.

## Source script (approved, fact-checked)
{roteiro_ptbr}

## Target

- Tone: {tom}
- Pace: {ppm} words per minute (the measured pace of the English voice)
- Length: {duracao_alvo_min} to {duracao_alvo_max} minutes
- Units: {unidades}

## Word limit per block

The English narration plays over the same video as the Portuguese one, block by block, so each English block has to fit in the time its Portuguese block takes. Each block has a hard ceiling on its `narracao`:

{limites_por_bloco}

Aim for 90 to 100% of each limit and never go over it. English says the same thing in fewer words than Portuguese, so fitting comes from tighter phrasing, not from dropping content. Cut padding ("in close quarters", "as we will see", "it is worth noting that"), not facts.

## What to change

1. **Units.** Convert to the target system, keeping the other in parentheses where precision matters.
2. **Cultural references.** A comparison that only lands for a Brazilian audience gets replaced by one that lands for the target audience — same rhetorical function, different referent.
3. **Rhythm.** English narration carries different sentence lengths. Re-break sentences for the voice, don't preserve Portuguese punctuation.
4. **Idiom.** Write English that was written in English.

## What must NOT change

1. **Every fact.** Same claims, same numbers, same attributions, same hedges. The script was fact-checked in Portuguese; the adaptation inherits that approval only if the facts survive intact.
2. **Uncertainty markers.** "Não sabemos" stays "we don't know". Never upgrade a hypothesis to a fact in translation.
3. **Structure.** Exactly the same number of blocks, in the same order, with the same beats inside each block and in the same order — both narrations share the same images, block by block.
4. **Point of view.** If the Portuguese narration speaks to the viewer in the second person ("você acorda..."), keep it ("you wake up...").
5. **No blood, no explicit death.**

## On-screen text (also adapted, never narrated)

- `titulo`: the chapter title shown on screen and listed in the description. Short, evocative, title case.
- `comentarios_mc`: the host's speech-balloon quips. Same count as the source block, same dry and ironic tone, 3 to 8 words each. Adapt the joke; do not translate it word for word.
- `tarjas`: location and era labels, same count as the source block, in UPPERCASE English (e.g. "ROMAN MARCHING CAMP, 1ST CENTURY").

## Output

Valid JSON, no code fences:

```
{{
  "titulo_provisorio": "...",
  "blocos": [
    {{"secao": "...", "titulo": "...", "narracao": "...", "afirmacoes_usadas": ["..."],
      "comentarios_mc": ["..."], "tarjas": ["..."]}}
  ],
  "notas_adaptacao": ["what you changed and why, one line each"],
  "palavras_total": 0
}}
```
