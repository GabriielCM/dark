---
id: livros/identificacao
version: 1
modelo_sugerido: rapido
descricao: Identifica metadados bibliograficos e estrutura de capitulos de um livro ingerido.
variaveis: [texto_inicial, sumario_detectado, nome_arquivo]
---
Identifique os dados bibliográficos desta obra a partir das primeiras páginas e do sumário detectado.

## Nome do arquivo
{nome_arquivo}

## Primeiras páginas
{texto_inicial}

## Sumário detectado automaticamente
{sumario_detectado}

## Regras

1. **Não invente.** Campo que não aparece no texto volta como `null`. Um ano de publicação chutado corrompe a classificação de direitos autorais, que é a decisão mais cara deste sistema.
2. **Tradutor é obrigatório de checar.** A tradução é obra separada: se o livro é traduzido, o nome do tradutor importa tanto quanto o do autor.
3. **Ano de morte do autor:** só preencha se aparecer no próprio texto (comum em edições de domínio público). Caso contrário, `null` — o sistema busca depois.
4. Distinga **ano de publicação original** de **ano desta edição**.

## Saída

JSON válido, sem cercas de código:

```
{{
  "titulo": "...",
  "subtitulo": "... ou null",
  "autor": "...",
  "autor_ano_morte": 1920,
  "tradutor": "... ou null",
  "tradutor_ano_morte": null,
  "idioma": "pt|en|...",
  "ano_publicacao_original": 1901,
  "ano_desta_edicao": 1998,
  "editora": "... ou null",
  "capitulos": [{{"numero": 1, "titulo": "...", "pagina_inicial": 12}}],
  "confianca": "alta|media|baixa",
  "observacoes": "o que ficou incerto"
}}
```
