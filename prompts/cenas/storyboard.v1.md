---
id: cenas/storyboard
version: 1
modelo_sugerido: rapido
descricao: Quebra o roteiro em cenas com duracao, prompt de cenario e pose do personagem.
variaveis: [roteiro, segundos_por_cena_min, segundos_por_cena_max, ppm, prompt_base_estilo, poses_disponiveis]
---
Quebre o roteiro abaixo em cenas para um vídeo 16:9. Cada cena é **uma imagem de cenário** que fica na tela enquanto a narração correspondente é falada.

## Roteiro
{roteiro}

## Parâmetros

- Duração por cena: {segundos_por_cena_min} a {segundos_por_cena_max} segundos
- Ritmo da narração: {ppm} palavras por minuto (use para estimar a duração de cada trecho)
- Prompt-base do estilo visual (todo prompt de cenário herda isto): {prompt_base_estilo}
- Poses disponíveis do personagem: {poses_disponiveis}

## Regras

1. **Corte nas fronteiras naturais** da narração — fim de frase ou de ideia, nunca no meio.
2. O prompt de cenário descreve **o lugar e a ação**, não o estilo. O estilo vem do prompt-base.
3. O personagem recorrente **não aparece em toda cena**. Use-o onde ele explica, aponta ou reage — cerca de uma cena em cada quatro. Cena sem personagem tem `personagem: null`.
4. **Movimento de câmera:** escolha `zoom_in`, `zoom_out`, `pan_left`, `pan_right` ou `estatica` conforme o conteúdo. Cenas de tensão pedem zoom lento; panoramas pedem pan.
5. **Camadas de profundidade:** descreva o que fica em `frente`, `meio` e `fundo`. É isso que gera o parallax 2.5D.
6. Nada de sangue, ferimento ou morte explícita nos prompts.
7. Nada de texto legível dentro da imagem.

## Saída

JSON válido, sem cercas de código:

```
{{
  "cenas": [
    {{
      "indice": 1,
      "narracao": "trecho literal do roteiro que toca nesta cena",
      "duracao_estimada_s": 9.0,
      "prompt_cenario": "wide view of a Roman aqueduct under construction, workers on wooden scaffolding, dry hills behind",
      "camadas": {{"frente": "...", "meio": "...", "fundo": "..."}},
      "camera": "zoom_in|zoom_out|pan_left|pan_right|estatica",
      "personagem": {{"pose": "apontando", "posicao": "direita"}},
      "sfx": "sugestão de efeito, ou null",
      "musica": "abertura|tensao|batalha|descoberta|fechamento|null"
    }}
  ]
}}
```
