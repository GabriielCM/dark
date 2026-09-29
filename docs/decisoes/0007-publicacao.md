# ADR 0007: Descrição, thumbnails e pacote de entrega montados por código

- **Status:** aceito
- **Data:** 29/09/2026
- **Depende de:** [ADR 0006](0006-referencias-commons.md)

## Contexto

O pacote de entrega antigo (`tests/fixtures/pacote_exemplo.txt`) saía quase inteiro do LLM, e mostra o que isso custava:

- **Aviso sem acento e desatualizado.** "Este video usa narracao e ilustracoes geradas por inteligencia artificial. A pesquisa, o roteiro e a revisao editorial sao humanos." Desde 09/2026 a pesquisa e o roteiro são feitos com auxílio de IA, na sessão do Claude Code, então o texto deixou de ser verdadeiro.
- **Fontes em dois formatos.** Em PT, só URLs; em EN, "Título (ano) — link".
- **Créditos copiados sem crítica.** Uma linha trazia "All rights reserved" junto de CC BY 2.0; outra, "autor nao informado".
- **Capítulos inventados pelo modelo.** Os carimbos de tempo não saíam do áudio, e a análise dos vídeos entregues achou um título de capítulo diferente do que aparecia na tela (`docs/estilo/analise-entregas.md`).
- **Uma thumbnail só, sem texto.** O texto era aplicado à mão.
- **Nenhuma checagem dos limites do YouTube.** Descrição com até 5.000 bytes, título com até 100 caracteres, tags com até 500, e `<` e `>` proibidos.

Decisões de alinhamento de 09/2026:
- thumbnails **por idioma, com e sem texto**, mais a arte base;
- fontes: **tudo o que passou no gate**, em "Título (ano): link";
- o aviso novo, com acentos e versão EN.

## Decisão

**O LLM escreve só o que é texto de verdade** (`prompts/metadados/pacote.v2.md`, modelo barato, uma chamada por idioma):
- título;
- dois títulos alternativos, para o "Testar e comparar";
- os dois parágrafos da descrição;
- as tags;
- o texto da thumb, com até 4 palavras.

A resposta fica em `metadados/llm.<lang>.json`. Se a etapa falhar depois da chamada, a retomada não paga de novo. Uma refação de metadados pedida na revisão apaga esse cache e manda o motivo do revisor no campo `{feedback_revisor}` do prompt.

**O resto da descrição é montado por código** (`publishing/description.py`), na ordem do pacote antigo:

| Seção | De onde vem |
|---|---|
| Parágrafos | LLM |
| Capítulos | Início real de cada bloco na narração (`narracao/tempos.<lang>.json`), com o mesmo título que aparece na tela |
| Fontes | As fontes citadas pelo relatório de fatos aprovado, na ordem da primeira citação, em "Título (ano): link" |
| Aviso | Texto fixo do canal (`config/canais/*.yaml`, `publicacao.textos`) |
| Créditos das ilustrações | Sidecar de cada cenário feito com img2img, em "Título — Autor — Licença — URL" |
| Créditos da música | Fase D |

Regras dos capítulos, que são as do YouTube:
- o primeiro é 00:00;
- são pelo menos 3;
- cada um dura 10 s ou mais. Um bloco mais curto passa a fazer parte do capítulo anterior.

**Limites** (`publishing/limits.py`), conferidos antes do pacote:
- **Descrição:** 5.000 bytes, porque a API conta bytes e acento ocupa dois. O que não cabe é cortado em cascata, do corte mais barato para o mais caro:
  1. títulos das fontes e dos créditos encurtados para 40 caracteres;
  2. fontes só com o link;
  3. créditos das ilustrações no `comentario_fixado.txt`.
- A música nunca sai da descrição: a faixa CC BY exige a atribuição nela.
- **Título:** até 100 caracteres, com aviso acima de 70.
- **Tags:** até 500 caracteres, contando as vírgulas e as aspas que o YouTube põe em volta das tags com espaço. As mais genéricas, que ficam no fim, caem primeiro.
- **Acentos:** o texto em PT é conferido contra uma lista de palavras que sempre levam acento.

**Thumbnails:**
- O conceito sai no storyboard, numa chamada a mais (`prompts/cenas/thumbnail.v1.md`): assunto, lado do texto e, quando ajuda, o MC reagindo.
- A arte é gerada com os cenários, em `assets/thumb-base.png`, e passa pela mesma revisão de imagens.
- O texto entra pelo Pillow (`publishing/thumbnails.py`), com a fonte e as cores das camadas do vídeo:
  - Comic Relief Bold, cor osso com contorno de tinta;
  - um degradê escuro no lado do texto;
  - o maior corpo que cabe no box, testando as quebras em 1 a 3 linhas;
  - o texto nunca é cortado, porque tirar uma palavra muda o sentido.
- A saída é JPEG em 1280×720, abaixo de 2 MB, em três arquivos: sem texto (igual para os dois idiomas) e com o texto de cada idioma.

**Pacote** (`entrega/`):
- `pacote de entrega.txt`, no formato do pacote antigo;
- `CHECKLIST.md`, com os avisos e o passo a passo do formulário;
- `pacote.json` e `thumb-base.png`;
- uma pasta por idioma, com `video.mp4`, `legendas.srt`, as duas thumbs e o `publicacao.txt`.

O `video.mp4` é hard link do vídeo da montagem. O backup pula esse nome, porque o original já é copiado.

## Alternativas consideradas

- **Deixar o LLM escrever a descrição inteira, como na v1.** Era o que já existia. O modelo teria de copiar 25 URLs sem errar nenhuma, inventaria os carimbos de tempo e escreveria sem acento de vez em quando: foram exatamente os defeitos do pacote antigo.
- **Texto dentro da imagem gerada.** O Z-Image escreve letras tortas. A análise das entregas achou texto embaralhado nos cenários, e por isso todo texto do canal é camada.
- **Gerar a arte da thumb na etapa de metadados.** Seria mais simples, mas ela escaparia da revisão de imagens, que é onde uma arte ruim deve ser pega.
- **Um provedor pago para a thumbnail.** Custo recorrente sem ganho demonstrado: a arte vem do mesmo gerador local dos cenários.
- **Copiar o vídeo para o pacote.** Dobraria o disco e o backup, de 1 a 2 GB por produção. O link simbólico exige permissão de administrador no Windows.

## Consequências

- **Descrição previsível.** Fora os dois parágrafos, a descrição é determinística, e mudar o formato é mudar código com teste. O pacote antigo virou fixture, e os testes comparam capítulos e créditos com ele.
- **Custo:** uma chamada barata a mais por vídeo, para o conceito da thumb (menos de US$ 0,001).
- **Capítulos dependem do áudio.** Um roteiro com menos de 3 blocos sai sem capítulos, e o checklist avisa.
- **Link colado pelo revisor, de fora do Commons (fase C2).** O crédito sai sem licença e o checklist lista o link para conferência.
- **Quando reavaliar:**
  - quando o "Testar e comparar" mostrar qual versão da thumb ganha (brief 5.4); a perdedora deixa de ser gerada;
  - quando o YouTube mudar algum limite.
