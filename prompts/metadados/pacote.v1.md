---
id: metadados/pacote
version: 1
modelo_sugerido: rapido
descricao: Gera titulo, descricao com fontes, tags, capitulos e conceito de thumbnail.
variaveis: [roteiro, fontes, cenas, idioma, divulgar_sintetico]
---
Gere os metadados de publicação para este vídeo. Escreva no idioma: {idioma}.

## Roteiro
{roteiro}

## Fontes usadas
{fontes}

## Cenas (para os capítulos)
{cenas}

## Regras

1. **Título:** até 70 caracteres. Concreto e específico. Sem clickbait, sem "VOCÊ NÃO VAI ACREDITAR", sem caixa alta gratuita. Um título bom promete exatamente o que o vídeo entrega.
2. **Descrição:** dois parágrafos sobre o conteúdo, depois os capítulos, depois a lista de fontes com URL. Se `{divulgar_sintetico}` for verdadeiro, inclua a linha de divulgação de conteúdo sintético ao final.
3. **Tags:** 12 a 15, da mais específica para a mais genérica.
4. **Capítulos:** de 5 a 8, começando obrigatoriamente em `00:00`. Título de capítulo descreve o conteúdo, não a estrutura ("A água que subia sozinha", não "Desenvolvimento").
5. **Thumbnail:** descreva o conceito visual em uma frase, no estilo do canal, e proponha um texto curto (até 4 palavras) — e também a versão sem texto, já que as duas serão testadas.

## Saída

JSON válido, sem cercas de código:

```
{{
  "titulo": "...",
  "titulos_alternativos": ["...", "..."],
  "descricao": "...",
  "tags": ["..."],
  "capitulos": [{{"tempo": "00:00", "titulo": "..."}}],
  "thumbnail": {{
    "conceito": "...",
    "prompt": "prompt de imagem no estilo do canal",
    "texto": "até 4 palavras",
    "versao_sem_texto": true
  }}
}}
```
