# ADR 0008: Narração antes do storyboard, com as cenas cortadas pela duração real

- **Status:** aceito; o ritmo (~6 s) foi revisto no [ADR 0012](0012-ritmo-de-3-segundos.md), que passa a ~3 s e corta também entre palavras
- **Data:** 30/09/2026
- **Depende de:** [ADR 0002](0002-fila-e-retomada.md)

## Contexto

A primeira amostra real de 60 s (29/09) ficou com 7 cenas de 7,8 s em média no PT e 9,0 s no EN, e o cartão final ficou 12 s na tela. Nos vídeos entregues, a imagem trocava a cada 6,2 s, com 164 de 185 cenas entre 4 e 8 s (`docs/estilo/analise-entregas.md`). A abertura antiga equivalente tem 9 cortes em 62 s.

Duas causas se somavam:
- **O storyboard estimava a duração.** A narração rodava depois das imagens, e o storyboard contava 150 palavras por minuto, mas o Kokoro `pm_santa` a 0,9 fala a ~165.
- **A regra de agrupamento era gulosa.** Ela juntava a próxima frase sempre que a cena tinha menos de 5 s, mesmo passando dos 7 s: 4,0 s + 7,1 s viraram o cartão de 12 s.

Aplicar a mesma regra sobre os tempos reais continuava dando 7,8 s. Consertar só a ordem não resolvia.

## Decisão

**1. A narração vem antes do storyboard.**

A nova ordem é `adaptacao_en` → `narracao` (6) → `cenas` (7) → `referencias` → `assets` → `pre_checagem` → `revisao_imagens` → `trilha` (12) → … A trilha continua andando enquanto a grade de imagens espera.

A espera é uma **dependência só de ordem** (`StepSpec.waits_for`):
- `cenas` só roda depois da narração;
- **refazer a narração não refaz o storyboard nem as imagens.** `downstream` segue só `depends_on`.

Isso vale porque a cena guarda texto, não segundos:
- as frases que cobre;
- a palavra em que começa (`inicio_palavra`);
- a fração do bloco que ocupa.

Com uma voz nova, a montagem recalcula os tempos (`scenes/timeline.py`). O corte pode ficar um pouco fora do alvo, e o aviso de ritmo da montagem mostra isso. Se incomodar, `refazer <id> cenas` corta de novo.

**2. O corte é feito por programação dinâmica sobre os tempos reais** (`scenes/grouping.py`).

É feito bloco a bloco, e a cena nunca atravessa um bloco.
- **Pontos de corte:**
  - o início de cada frase;
  - numa frase acima de `corte_em_virgula_acima_s` (8 s, em PT ou na estimativa EN), também depois de uma vírgula, de um ponto e vírgula, de dois-pontos ou antes de um travessão, onde a voz já pausa.
- **Durações:**
  - PT: o tempo real de cada palavra (`narracao/tempos.pt-br.json`, cuja entrada de cada frase ganhou a faixa `palavras`);
  - EN: a duração do bloco EN vezes a fração de palavras, a mesma regra que a montagem usa.
- **Custo por cena:**
  - `(d − alvo)² / 2` em cada idioma;
  - uma penalidade forte fora de `[min, max]` em qualquer idioma;
  - +1 quando a cena começa no meio de uma frase.
- **Configuração** (`app.yaml`, bloco `cenas`): alvo de 6 s e faixa de 4 a 8 s. Desde o [ADR 0012](0012-ritmo-de-3-segundos.md), 3 s, de 2 a 4,5 s, e 2,5 s no primeiro minuto.
- **Fallback:** sem narração (produção antiga, teste), a duração volta a ser estimada pelas palavras por minuto do canal. O storyboard registra qual caminho usou em `tempos`.

**3. O corte do EN cai numa fronteira.**

A cena EN começa na fração do bloco, encaixada:
- no início de frase EN mais próximo, até 1 s de distância;
- senão, no início de palavra mais próximo.

Antes, ela podia começar no meio de uma palavra.

## Alternativas consideradas

- **Só mover a narração.** Com a regra gulosa, a média continuava em 7,8 s.
- **Cortar só entre frases.** É mais simples, mas uma frase de 8 a 10 s vira uma cena longa. Com a regra atual, a vírgula só entra quando a frase passa de 8 s.
- **Alvo só no PT.** O EN da amostra saiu 15% mais longo, o que dá cenas de ~7 s no EN. O alvo na média dos dois idiomas deixa o PT em ~5,5 s e o EN em ~6,3 s.
- **Gravar segundos no storyboard.** A montagem não precisaria recalcular nada, mas qualquer refação da voz invalidaria o storyboard e, com ele, as imagens: umas 190 imagens a 26 s cada.

## Consequências

- **Na amostra de 29/09**, com os mesmos tempos:
  - antes: 7 cenas, 7,8 s em PT e 9,0 s no EN, cartão final de 12 s;
  - agora: 10 cenas, 5,5 s em PT e 6,2 s no EN, nenhuma cena acima de 8 s em PT e a última com 6,8 s.
- **A narração passa a rodar antes de o ComfyUI ocupar a GPU**, o que evita a disputa de VRAM entre o Kokoro e o Z-Image.
- **Uma cena pode começar no meio de uma frase longa.** A narração da cena, que a grade de imagens e o storyboard mostram, é o recorte exato das palavras.
- **Reavaliar** se a primeira produção de 20 minutos sair fora de 5 a 7 s de média, ou se o corte em vírgula parecer picotado no lado a lado.
