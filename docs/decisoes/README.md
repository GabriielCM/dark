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
