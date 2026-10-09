# Decisões de arquitetura (ADRs)

Um arquivo por decisão, numerado em sequência. Decisão de produto vai para o brief; decisão técnica vem para cá.

| # | Título | Status |
|---|---|---|
| [0001](0001-stack.md) | Stack do orquestrador e do painel | aceito |
| [0002](0002-fila-e-retomada.md) | Fila de etapas, idempotência e retomada | aceito |
| [0003](0003-custos-e-teto.md) | Registrador de custos e teto de orçamento | aceito |
| [0004](0004-backup-local.md) | Backup local e rotina de commit | aceito |
| [0005](0005-comfyui-z-image.md) | Cenários com Z-Image Turbo no ComfyUI local | aceito |
| [0006](0006-referencias-commons.md) | Fotos de referência do Wikimedia Commons para o img2img | aceito |
| [0007](0007-publicacao.md) | Descrição, thumbnails e pacote de entrega montados por código | aceito |
| [0008](0008-narracao-antes-das-cenas.md) | Narração antes do storyboard, com as cenas cortadas pela duração real | aceito |
| [0009](0009-esteira-e-pagina-da-producao.md) | A esteira e a página da produção | aceito |
| [0010](0010-cortes-tiktok.md) | Cortes verticais para o TikTok | aceito |
| [0011](0011-faixa-unica-de-audio.md) | Um vídeo com duas faixas de áudio, na mesma linha do tempo | aceito para teste |
| [0012](0012-ritmo-de-3-segundos.md) | Ritmo de ~3 s por imagem, com corte seco | aceito para teste |

## Modelo

```markdown
# ADR NNNN: título

- **Status:** proposto | aceito | substituído por ADR NNNN
- **Data:** DD/MM/AAAA

## Contexto
O que forçou a decisão.

## Decisão
O que foi decidido, no presente do indicativo.

## Alternativas consideradas
O que foi descartado e por quê. Esta seção é a que tem valor daqui a seis meses.

## Consequências
O que fica melhor, o que fica pior, e qual evento manda reavaliar.
```
