# ADR 0003: Registrador de custos e teto de orçamento

- **Status:** aceito
- **Data:** 10/09/2026
- **Depende de:** [ADR 0001](0001-stack.md)

## Contexto

O brief (princípio 4) diz: "o orçamento é limite duro. O custo é registrado por etapa e por vídeo, e o teto mensal bloqueia chamadas pagas". US$ 50/mês, com a operação esperada perto de US$ 5 a 13.

Um teto que só avisa não é um teto.

## Decisão

**Nenhuma chamada paga acontece fora do registrador.** A trava fica no ponto de chamada, não na revisão posterior.

```python
async with costs.guard(step="roteiro", provider="openrouter",
                       model="...", video_id=vid) as entry:
    resp = await client.chat(...)
    entry.record(input_tokens=..., output_tokens=...)
```

O `guard`:

1. **Antes:** consulta o gasto do mês. Se já passou do teto, levanta `BudgetExceeded` e a chamada não sai. Se a *estimativa* desta chamada ultrapassaria o teto, também bloqueia.
2. **Durante:** deixa o adaptador rodar.
3. **Depois:** grava uma linha em `cost_entries` com etapa, provedor, modelo, unidades, valor em USD, `video_id` e o `step_run_id`.

Provedores locais registram uma linha com `amount_usd = 0` e `local = true`. Isso é de propósito: dá para responder "quantos cenários o FLUX gerou este mês" sem pagar nada por isso.

### Preço vem de tabela versionada

`config/precos.yaml` guarda preço por provedor/modelo/unidade, com data de vigência. O código nunca traz número embutido. Modelo sem preço na tabela é tratado como **desconhecido, portanto bloqueado** em modo `strict` (padrão), porque um preço que não sabemos é um preço que não cabe no teto.

**Atualizado em 04/10/2026.** Quando o provedor informa o valor cobrado na resposta, é esse valor que vai para `cost_entries`. O OpenRouter faz isso em `usage.cost`. A tabela continua obrigatória e decide, antes da chamada, se ela cabe no teto. Depois da chamada, a conta pela tabela fica no detalhe da linha (`usd_pela_tabela`), e uma divergência acima de 20% gera um aviso no log para atualizar a tabela. O motivo: a tabela estava 50% acima do preço do Sonnet 5, e o relatório mostrava mais do que a fatura. Sem valor informado, como no ElevenLabs ou numa resposta sem o campo, vale a conta pela tabela, como antes.

### Três níveis

| Nível | Padrão | Efeito |
|---|---|---|
| `soft_limit_usd` | 35 | Avisa no painel, continua |
| `hard_limit_usd` | 50 | Bloqueia chamadas pagas; locais seguem |
| `per_video_limit_usd` | 5 | Bloqueia o vídeo específico, não o mês |

Todos configuráveis. O teto por vídeo pega o caso do roteiro que entra em laço de reescrita no gate de fatos e consome sozinho o mês.

### Mês é mês do calendário, em UTC

Simples de explicar e de testar. `2026-09-01T00:00:00Z` a `2026-09-30T23:59:59Z`.

## Alternativas consideradas

- **Registrar depois, no adaptador, sem trava.** É o que quase todo projeto faz e é como se estoura orçamento. Rejeitado.
- **Teto por dia.** Rejeitado: o volume é irregular por natureza (um lote de 3 roteiros num sábado é normal) e um teto diário criaria bloqueio falso.
- **Contar tokens antes de chamar para estimar exato.** Feito só onde é barato (texto, via `tiktoken` aproximado). Para imagem e TTS a unidade é conhecida de antemão (imagens, caracteres), então a estimativa é exata.

## Consequências

- Adicionar um provedor pago exige adicionar preço em `config/precos.yaml`. Fricção deliberada.
- O painel mostra gasto por mês, por vídeo e por etapa sem nenhum trabalho extra: é uma consulta na mesma tabela.
- Se o teto bloquear no meio de um vídeo, ele fica `blocked` e retoma sozinho quando o mês virar ou o teto for elevado — e como as etapas são idempotentes (ADR 0002), não se perde nada do que já foi pago.
