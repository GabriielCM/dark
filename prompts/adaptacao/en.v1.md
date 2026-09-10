---
id: adaptacao/en
version: 1
modelo_sugerido: principal
descricao: Adapta (nao traduz) o roteiro PT-BR aprovado para o canal em ingles.
variaveis: [roteiro_ptbr, ppm, duracao_alvo_min, duracao_alvo_max, unidades, tom]
---
Adapt this Brazilian Portuguese documentary script for an English-language channel. This is an **adaptation, not a translation**.

## Source script (approved, fact-checked)
{roteiro_ptbr}

## Target

- Tone: {tom}
- Pace: {ppm} words per minute
- Length: {duracao_alvo_min} to {duracao_alvo_max} minutes
- Units: {unidades}

## What to change

1. **Units.** Convert to the target system, keeping the other in parentheses where precision matters.
2. **Cultural references.** A comparison that only lands for a Brazilian audience gets replaced by one that lands for the target audience — same rhetorical function, different referent.
3. **Rhythm.** English narration carries different sentence lengths. Re-break sentences for the voice, don't preserve Portuguese punctuation.
4. **Idiom.** Write English that was written in English.

## What must NOT change

1. **Every fact.** Same claims, same numbers, same attributions, same hedges. The script was fact-checked in Portuguese; the adaptation inherits that approval only if the facts survive intact.
2. **Uncertainty markers.** "Não sabemos" stays "we don't know". Never upgrade a hypothesis to a fact in translation.
3. **Structure.** Same blocks, same order, same beats — the two videos share images and timing.
4. **No blood, no explicit death.**

## Output

Valid JSON, no code fences:

```
{{
  "titulo_provisorio": "...",
  "blocos": [
    {{"secao": "...", "titulo": "...", "narracao": "...", "afirmacoes_usadas": ["..."]}}
  ],
  "notas_adaptacao": ["what you changed and why, one line each"],
  "palavras_total": 0
}}
```
