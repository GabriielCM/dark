# ADR 0002: Fila de etapas, idempotência e retomada

- **Status:** aceito
- **Data:** 10/09/2026
- **Depende de:** [ADR 0001](0001-stack.md)

## Contexto

O `CLAUDE.md` exige que as etapas sejam "idempotentes e retomáveis: se algo falhar, o pipeline retoma da última etapa concluída sem repetir chamadas pagas". Um vídeo custa entre US$ 0,50 e US$ 9. Repetir a narração porque a montagem quebrou é queimar orçamento por um erro de engenharia.

## Decisão

**Idempotência por artefato, não por memória.** Uma etapa é considerada concluída quando seus artefatos de saída existem no disco e o sidecar correspondente valida. A fila em SQLite guarda o estado, mas a verdade está nos arquivos.

Cada etapa declara:

```python
class Step(Protocol):
    name: StepName
    depends_on: tuple[StepName, ...]
    def outputs(self, ctx: StepContext) -> list[Path]: ...   # o que ela produz
    async def run(self, ctx: StepContext) -> StepResult: ...  # como produz
```

O runner, antes de executar:

1. Confere `depends_on` — todas `done`?
2. Chama `outputs()` e verifica se todos os caminhos existem e têm sidecar íntegro. Se sim: marca `done`, **não executa**, custo zero.
3. Se não, adquire o lease e executa.

Consequência prática: apagar `videos/<id>/narracao/` e re-enfileirar refaz só a narração. É essa a interface de "refazer uma etapa".

### Lease em vez de bloqueio

`running` carrega `lease_until` e `worker_id`. Um lease vencido (padrão: 30 minutos) volta a etapa para `pending`. Se o processo morre no meio, a etapa se recupera sozinha na próxima varredura, sem intervenção e sem um lock file preso.

### Retentativa

`attempts` cresce a cada falha. O runner reagenda com espera exponencial (30 s, 2 min, 8 min) até `max_attempts` (padrão 3), e então marca `failed`, que é um estado visível no painel. Erros marcados como `PermanentError` não são retentados — chave de API inválida não melhora esperando.

### Granularidade fina dentro da etapa

A etapa `assets` gera ~90 cenários. Falhar no de número 87 e refazer os 86 seria absurdo. Etapas com itens repetidos gravam cada item como seu próprio artefato (`assets/cena-087.png` + sidecar) e pulam os que já existem. A idempotência vale por item, não só por etapa.

## Alternativas consideradas

- **Estado só no banco.** Rejeitado: fica dessincronizado do disco na primeira vez que alguém apaga um arquivo à mão, e apagar um arquivo à mão é exatamente como se corrige um cenário ruim.
- **Hash de entrada para invalidar cache.** Elegante, e adotado parcialmente: o sidecar guarda o hash das entradas e da versão do prompt. Mas invalidação automática ao mudar prompt refaria trabalho pago sem aviso, então a divergência é apenas *sinalizada* no painel; refazer continua sendo um ato explícito.
- **Fila em memória.** Rejeitado: perde tudo ao fechar o processo, que é o caso comum numa máquina de trabalho.

## Consequências

- Refazer uma etapa é apagar um diretório. Simples de documentar, simples de operar.
- O disco vira parte do estado do sistema — o backup dos artefatos (brief, seção 11) deixa de ser opcional.
- Etapas precisam declarar as saídas honestamente. Uma etapa que esquece um arquivo em `outputs()` será reexecutada à toa; uma que declara demais será pulada sem ter terminado. Há teste para isso.
