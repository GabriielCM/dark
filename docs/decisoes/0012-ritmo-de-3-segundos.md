# ADR 0012: Ritmo de ~3 s por imagem, com corte seco

- **Status:** aceito para teste no próximo vídeo
- **Data:** 09/10/2026
- **Depende de:** [ADR 0008](0008-narracao-antes-das-cenas.md), [ADR 0010](0010-cortes-tiktok.md)
- **Revisa:** o ritmo de ~6 s do ADR 0008. O corte por programação dinâmica continua o mesmo.

## Contexto

Os cortes do TikTok reaproveitam as cenas do storyboard (ADR 0010), então o ritmo deles é o do vídeo.

**Os cortes do Gizé:**
- uma imagem a cada 5,8 s, cerca de 10 trocas por minuto;
- de 7 a 9 cenas por corte com a câmera `estatica`;
- cada troca escurecia por 0,8 s (12 quadros na saída e 12 na entrada).

O usuário achou o ritmo lento para a plataforma, principalmente nos vídeos de 1 minuto, e aceitou um tempo de produção maior para ter mais imagens.

**O que o storyboard do Gizé mostra:**
- 209 cenas de 5,65 s em média;
- 121 delas com a câmera `estatica`;
- cerca de 28 s por imagem no ComfyUI (mediana medida nos sidecars), 1h45 de GPU por vídeo.

**Por que é preciso cortar entre palavras:**
- as frases do Gizé têm 3,5 s de mediana, e 101 de 267 passam de 4,5 s;
- o alinhamento devolve as palavras coladas, com pausa mediana de 0,00 s entre elas, então a pontuação é o único sinal de respiro;
- com cortes só nas vírgulas, 60 cenas ficam acima do máximo.

## Decisão

**1. Ritmo** (bloco `cenas` do `app.yaml`):
- **Vídeo inteiro:** alvo de 3 s, de 2 a 4,5 s.
- **Primeiro minuto** (`abertura`): alvo de 2,5 s, de 1,8 a 3,5 s. É onde a retenção do concreto caía para ~70%.
- **Como as faixas se aplicam** (`PaceBands`): cada cena candidata usa o ritmo do ponto em que começa. A programação dinâmica continua exata.

**2. Corte dentro da frase:**
- **Quando:** só numa frase mais longa que o máximo do trecho em que ela começa. O `corte_em_virgula_acima_s` deixa de ser fixo.
- **Onde, do mais barato ao mais caro:**

| Ponto de corte | Custo |
|---|---|
| Pontuação (vírgula, ponto e vírgula, dois-pontos, antes de travessão) | 1,0 |
| Antes de conjunção (`e, que, mas, quando, porque…`) | 1,5 |
| Entre duas palavras quaisquer | 2,5 |

- **Onde nunca:**
  - a menos de 2 palavras das pontas da frase;
  - depois de número;
  - depois de palavra de até 3 letras;
  - depois de uma palavra que pede a seguinte (`para`, `cada`, `foi`, `muito`…).

**3. Storyboard v7** (`prompts/cenas/storyboard.v7.md`):
- **Ritmo:** a faixa de segundos vem da configuração (`{ritmo}`).
- **Frase continuada:** a cena com `continua_frase: true` é outro plano do mesmo momento (geral → médio → detalhe, ação → reação, lugar → objeto), com descrição diferente.
- **Tempo mínimo:**
  - cartão só em cena de 3 s ou mais;
  - balão também a partir de 3 s, mas o código aceita a partir de 2,5 s e passa o balão de uma cena curta para a seguinte (`move_acted_balloons`).
- **Texto-chave:** no máximo um a cada ~10 s.
- **MC:** fica do mesmo lado em cenas seguidas.
- **Câmera:** no máximo duas `estatica` seguidas. O código garante isso (`vary_static_cameras`).
- **Limite de saída do LLM:** acompanha o número de cenas do bloco (`2000 + 400 × cenas`, no mínimo 12 mil).

**4. Transições:**
- **No YouTube:** corte seco entre as cenas; só a troca de capítulo (e a entrada e a saída do vídeo) escurece.
- **Nos cortes do TikTok:** corte seco em tudo.
- **Quem decide:** o Python, por `fadeIn` e `fadeOut` em `SceneProps`.
- **Produções antigas:** o storyboard novo leva `transicoes: capitulos`. Um storyboard sem a marca continua escurecendo a cada cena, então uma remontagem não muda o visual de uma produção de ~6 s.

**5. Remotion:**
- **Fade:** o novo cabe em 1/3 da cena. O antigo quebrava o `interpolate` em cena abaixo de 0,8 s, o que a cena EN alinhada já podia produzir.
- **Duração das sequências:** sai da diferença entre os inícios arredondados, para não abrir um quadro vazio que piscaria no corte seco.
- **Camadas:** texto e balão entram 0,3 s depois do corte seco (antes, 0,8 s, esperando o fade).
- **MC:** não entra de novo quando continua na cena seguinte, no mesmo lugar.
- **Movimento de câmera:** a amplitude acompanha a duração (metade numa cena de 3 s), para a câmera manter a velocidade de hoje em vez de virar chicote.

**6. Pré-checagem da sessão:**
- `imagens folhas <id> [--capitulo N]` monta folhas de 12 miniaturas, na ordem e com os capítulos da grade, em `data/cache/folhas/<id>/`.
- A sessão confere por elas e abre o PNG só das suspeitas.
- A revisão do usuário continua na grade.

## Alternativas consideradas

- **Imagens extras só nos trechos dos cortes, com o YouTube a ~6 s.** Daria o ritmo de ~24 trocas por minuto no TikTok com menos imagens. Mas a escolha dos cortes teria de vir antes das imagens, e trocar um corte depois exigiria imagens novas fora da grade. O usuário preferiu acelerar o vídeo inteiro e avaliar o TikTok depois.
- **Cortes só na pontuação:** 60 cenas fora da faixa no Gizé, até 8,2 s.
- **Usar as pausas entre palavras:** elas não existem no alinhamento (mediana de 0,00 s).
- **Abertura igual ao bloco 0:** o tamanho do bloco varia; o relógio é o que importa para a retenção.
- **Fusão rápida entre as cenas:** exigiria sobrepor as sequências no Remotion. O corte seco é o padrão do formato, e o escurecimento ficou para a troca de capítulo, onde marca a passagem.
- **Partir o storyboard em várias chamadas por bloco:** o bloco mais longo do Gizé dá ~44 cenas, e o modelo rápido devolve isso numa chamada só, com mais limite de saída.

## Consequências

**Simulado com os tempos reais do Gizé:**
- 400 cenas, contra 209;
- abertura com 2,46 s em média, o resto com 2,99 s;
- 10 cenas fora da faixa, quase todas frases curtas entre frases longas;
- metade das cenas começa no meio de uma frase.

**Custos:**
- **GPU:** ~400 imagens a ~28 s, cerca de 3h05 por vídeo (antes, 1h45). Com a faixa única, as imagens servem às duas narrações, como antes.
- **LLM:** o storyboard sobe ~US$ 0,08 por vídeo, ~US$ 1 por mês.
- **Fallback pago de imagem:** se entrar no lugar do ComfyUI, ~400 imagens a US$ 0,013 dão ~US$ 5 por vídeo, o teto por vídeo. Só com aprovação.

**Revisão:**
- a grade e a pré-checagem da sessão dobram de tamanho;
- as folhas reduzem o trabalho da sessão; o do usuário cresce.

**Fotos do Commons:** devem passar de ~30 para ~55 por vídeo, o que deixa a etapa `referencias` mais longa.

**Produções existentes:**
- não mudam, a não ser que o storyboard seja refeito;
- refazer `cenas` regera todas as imagens, porque as sementes são por índice de cena.

**Reavaliar depois do primeiro vídeo completo:**
- o ritmo no YouTube (retenção do primeiro minuto e média);
- o ritmo nos cortes do TikTok (~20 trocas por minuto); se ainda parecer lento, baixar o alvo só pela configuração;
- se a revisão da grade passar do tempo que o usuário tem.
