# Biblioteca do personagem

SVGs do personagem recorrente: poses, expressoes e gestos, com as partes
separadas para animacao (brief 5.2). Gerada **uma unica vez** — a cada video so
se gera roteiro, narracao, cenarios e legendas.

Enquanto o personagem nao for definido (brief, secao 12), este diretorio fica
vazio e as cenas saem sem ele. Nada quebra.

## Como o pipeline encontra os SVGs

Duas formas, nesta ordem:

1. `index.json` mapeando pose para arquivo:
   ```json
   {"apontando": "personagem/apontando.svg", "explicando": "personagem/explicando.svg"}
   ```
2. Sem `index.json`, o nome do arquivo e a pose: `apontando.svg` -> pose `apontando`.

As poses que o storyboard pode pedir estao em `config/estilo/guia.yaml`, em
`personagem.poses_minimas`.
