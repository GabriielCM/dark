# ADR 0004: Backup local e rotina de commit

- **Status:** aceito
- **Data:** 29/09/2026

## Contexto

Em setembro de 2026, a partição que guardava o projeto falhou depois de uma queda de energia. A tentativa de recuperação com TestDisk não deu certo. Perderam-se:

- cerca de 19 dias de código que não estava no git;
- os vídeos originais;
- os workflows do ComfyUI;
- as configurações de voz e estilo.

O que restou foi o commit inicial no GitHub e os vídeos publicados no YouTube.

O brief (seção 11) já listava "máquina única com armazenamento local sem backup" como risco, com a rotina ainda pendente.

## Decisão

O código e o que vai para o git são publicados **no GitHub ao fim de cada fase**, com commit e push na branch de trabalho. Nada fica só no disco.

O resto é espelhado **todo dia no D:**, que é um HD físico separado do SSD do sistema. Isso é feito pelo comando `mundoantigo backup` (`src/mundoantigo/ops/backup.py`):

| Origem | Como |
|---|---|
| Banco SQLite | API de backup do SQLite: a cópia sai consistente mesmo com o worker escrevendo |
| `videos/`, `biblioteca/`, `livros/`, `data/` | Espelho com `robocopy /MIR`, copiando só o que mudou; o arquivo cru do SQLite fica de fora |
| `.env` | Cópia simples, para que uma reinstalação não dependa de reconstruir as chaves |
| `backup.extras` | Pesos dos modelos (`C:/dev/modelos`) e as entregas antigas |

- O destino vem de `backup.destino` no `app.yaml`, que o `MA_BACKUP_DESTINO` no `.env` sobrescreve.
- Cada execução grava `manifesto.json` e acrescenta uma linha ao `historico.jsonl` no destino.
- Uma tarefa agendada do usuário, que não exige admin, roda o backup todo dia às 12:30 via `scripts/registrar-tarefas.ps1`. Se o PC estiver desligado no horário, a tarefa roda assim que ele ligar.

## Alternativas consideradas

- **Só git.** Não cobre vídeos, bibliotecas de áudio, banco nem pesos de modelo, que não cabem no git e não devem ir para ele.
- **Nuvem paga (~US$ 2/mês).** O usuário escolheu ficar só com o D:. Custo recorrente novo entra no teto e exige aprovação (CLAUDE.md).
- **Copiar o arquivo `.sqlite3` direto.** Com o worker escrevendo, a cópia pode sair corrompida. A API de backup do SQLite existe para isso.
- **Deixar os pesos dos modelos de fora, já que podem ser baixados de novo.** São cerca de 25 GB, e o `robocopy` só copia uma vez. Depois da primeira execução, o custo é zero, e numa reinstalação eles economizam horas de download.

## Consequências

- Uma falha do SSD custa no máximo um dia de artefatos, e zero de código, se o push de fim de fase for respeitado.
- O D: está na mesma máquina, então roubo, incêndio ou pico de energia que queime os dois discos não estão cobertos. Reavaliar a nuvem quando os canais gerarem receita.
- O `.env` fica em texto claro no D:, exatamente como já está no C:. Se o D: sair da máquina, por exemplo como disco externo, isso precisa ser revisto.
