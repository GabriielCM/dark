# Projeto Remotion

Montagem dos videos. Roda como processo separado, chamado pelo orquestrador em
Python (ver [ADR 0001](../docs/decisoes/0001-stack.md)).

## Instalar

```bash
npm ci
```

## O contrato

O Python escreve `videos/<video_id>/montagem/props.<lang>.json` e chama:

```bash
npx remotion render src/index.ts Video <saida.mp4> \
  --props=<props.json> --public-dir=videos/<video_id>
```

O `--public-dir` faz `staticFile("assets/cena-001.png")` resolver dentro do
diretorio daquele video, sem copiar nada para ca.

O formato das props vive em dois lugares que precisam concordar:

- `src/types.ts` (aqui)
- `src/mundoantigo/render/props.py` (la)

`npm run contrato -- <contrato.json>` compara os dois. O teste
`tests/test_render_contract.py` gera o snapshot e roda essa comparacao.

## Desenvolver

```bash
npm run studio      # abre o Studio com props de exemplo
npm run typecheck
```

Para abrir o Studio com um video de verdade, aponte o `--props` para o JSON
gerado pelo pipeline.
