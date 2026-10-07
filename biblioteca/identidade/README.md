# Identidade dos canais

Foto de perfil e capas do YouTube, as mesmas para as contas do TikTok
([ADR 0010](../../docs/decisoes/0010-cortes-tiktok.md)). Os originais se perderam
na falha de disco de 09/2026 e foram regerados em 06/10/2026 a partir de um print
do canal EN. As imagens ficam fora do git e vão para o backup no D:
([ADR 0004](../../docs/decisoes/0004-backup-local.md)). Cada uma tem um sidecar
`.meta.json` com origem, semente e prompt.

| Arquivo | Tamanho | O que é |
|---|---|---|
| `avatar.png` | 1080x1080 | Rosto do MC em fundo laranja chapado (#F1A05C), igual nos dois canais |
| `capa-en.jpg` | 2560x1440 | "How the Ancient World Worked" / "Ancient history, from the inside" |
| `capa-pt.jpg` | 2560x1440 | "Mundo Antigo" / "Como o mundo antigo realmente funcionava" |

## Como foram feitas

- **Imagens:** geradas no ComfyUI local com o guia de estilo (b-sombreado) e a descrição fixa do MC (`config/estilo/guia.yaml`).
  - Foto: o MC de túnica creme e alça de couro, na semente 33.
  - Fundo da capa: um porto antigo, com barcos à esquerda e um templo de colunas à direita, na semente 11, ampliado para 2560x1440.
- **MC da capa:** a pose `apontando` com o figurino padrão, gerada por
  `uv run mundoantigo personagem poses --figurino "a plain cream linen tunic with a brown leather belt" --poses apontando`.
- **Texto:** composto por código, nunca dentro da imagem gerada. A placa é creme com borda escura. O título vai em Baloo 2 peso 800, laranja (#C4582E) com contorno escuro, e a frase em Comic Relief Bold. As fontes estão em `render/src/fonts/`.
- **Área segura:** a placa e o MC ficam no retângulo central de 1546x423, o que aparece em todo aparelho.
- **Recorte da foto:** o rembg deixava o rosto translúcido. Funcionou pintar o fundo liso a partir das bordas, porque o contorno grosso do desenho segura a tinta.
