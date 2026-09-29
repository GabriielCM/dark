---
id: cenas/thumbnail
version: 1
modelo_sugerido: rapido
descricao: "Conceito visual da thumbnail, decidido junto com o storyboard para a arte sair com os cenarios e passar pela mesma revisao."
variaveis: [titulo, gancho, capitulos, personagem, figurino]
---
Proponha a thumbnail deste vídeo: você é o diretor de arte de um canal de documentários ilustrados de história antiga, em estilo cartunesco com contorno grosso.

## O vídeo

- Título de trabalho: {titulo}
- Gancho: {gancho}
- Capítulos: {capitulos}

## O apresentador

{personagem}, vestindo {figurino}. Ele pode aparecer na thumbnail reagindo ao assunto, com uma expressão forte e legível de longe. Use-o quando isso ajudar; deixe-o de fora quando o objeto ou o lugar sozinho contar a história melhor.

## Regras

1. **Um assunto só**, grande e claro, que se entenda numa miniatura do tamanho de um selo.
2. **Um lado livre.** Um terço da imagem, à esquerda ou à direita, fica simples (céu, parede lisa, fundo desfocado): ali entra o texto, que é aplicado depois. A imagem em si não tem nenhuma letra.
3. **Sem sangue, feridos ou mortos**, mesmo em tema de batalha: o canal precisa ser adequado a anunciantes.
4. **Nada de personagens, marcas ou estilos de estúdios e artistas existentes.**
5. A `descricao_visual` é em inglês, porque vai direto para o gerador de imagens: descreva o assunto, a composição e a luz, sem nomear o estilo, que já é acrescentado depois.

## Saída

JSON válido, sem cercas de código:

```
{{
  "conceito": "uma frase em português, para o revisor",
  "descricao_visual": "in English: subject, composition, lighting",
  "mc": {{"acao": "in English: what he does", "expressao": "in English: one or two words"}},
  "lado_texto": "esquerda"
}}
```

Use `"mc": null` quando o apresentador não aparecer. `lado_texto` é `"esquerda"` ou `"direita"`.
