# ADR 0010: Cortes verticais para o TikTok

- **Status:** aceito
- **Data:** 06/10/2026
- **Depende de:** [ADR 0007](0007-publicacao.md), [ADR 0008](0008-narracao-antes-das-cenas.md), [ADR 0009](0009-esteira-e-pagina-da-producao.md)

## Contexto

O gargalo dos canais é a distribuição. O vídeo do concreto teve 53% de retenção, mas 931 impressões, quase todas vindas de vídeos sugeridos. Em 06/10/2026 o usuário decidiu abrir duas contas no TikTok, uma PT e uma EN, com o mesmo nome e @ dos canais do YouTube.

As regras que pesam, conferidas em 10/2026 em fontes de terceiros (as páginas oficiais da TikTok só abrem no app):
- O Programa de Recompensas para Criadores aceita o Brasil. Exige conta pessoal, 10 mil seguidores e 100 mil views em 30 dias.
- **Só paga vídeo com mais de 1 minuto.** Uma view só conta depois de 5 s no Para Você.
- O pagamento pesa originalidade, tempo assistido, valor de busca e engajamento. A busca lê a legenda, o texto na tela e a fala.

O usuário só revisa, e o resto é automático. Ele também duvida que quem vê um corte no Brasil saia do TikTok para o YouTube. Por isso o vídeo inteiro vai para o TikTok junto com os cortes, fixado no perfil, e os cortes apontam para ele.

## Decisão

**Uma etapa nova, a 15ª: `cortes`.** O pipeline passa a ter 17 etapas: `revisao` vira a 16ª e `entregue` a 17ª.
- A etapa depende de `revisao_imagens` e `trilha` e espera a `montagem` só por ordem, porque o vídeo principal sai primeiro.
- Refazer a montagem não refaz os cortes. Refazer imagens ou voz refaz.
- É `gpu_bound`, porque renderiza, e `can_spend`, porque chama o LLM.
- `revisao` depende dela.

**O código mede, o LLM escolhe** (`clips/`):
- **Candidatos** (`candidates.py`):
  - trechos de frases inteiras dentro de um bloco do roteiro, que é a unidade que se sustenta sozinha;
  - o trecho começa no início do bloco ou numa frase que abre uma cena, para a imagem trocar junto com a voz, com pelo menos 15 s entre dois inícios do mesmo bloco;
  - para cada início, duas opções de fim: a frase mais distante que cabe e a mais perto do meio da faixa;
  - **PT de 65 a 100 s e EN de 65 a 115 s.** O mínimo PT é 65 s, e não 70, para o bloco de abertura (o gancho, ~68 s nas Pirâmides) caber;
  - o EN fica na mesma fração do bloco que o PT, como as cenas no ADR 0008, encaixado no início e no fim de frase EN mais próximos;
  - um respiro de 0,15 s antes e 0,4 s depois, que para no meio da pausa, de modo que dois cortes vizinhos nunca dividem um instante.
- **Escolha** (`prompts/cortes/selecao.v1.md`, modelo rápido, ~US$ 0,01 por vídeo): o LLM recebe os candidatos com o texto PT e EN e devolve:
  - 3 trechos, de preferência de blocos e assuntos diferentes;
  - por trecho e idioma, o **gancho na tela** (até 8 palavras, tirado do próprio trecho, sem narração nova, para nenhuma afirmação escapar do gate de fatos), a legenda do post e as hashtags;
  - a legenda do vídeo inteiro.
  A resposta fica em `cortes/llm.json`. Um motivo de rejeição com a etapa `cortes` vai para o prompt.
- **Conferência** (`selection.py`, antes de qualquer render):
  - o candidato existe e não há sobreposição;
  - há gancho e legenda nos dois idiomas;
  - as hashtags saem normalizadas (`#Império Romano` vira `#imperioromano`), com a fixa do canal primeiro (`tiktok.hashtag_fixa`) e no máximo 5;
  - os cortes ficam na ordem do vídeo.
  O resultado é `cortes/selecao.json`. Escolha inválida apaga o cache e a retomada pergunta de novo.

**O render parte das cenas, não do mp4** (`render/clips.py`):
- As props do vídeo inteiro saem em 1080x1920, recortadas no intervalo e começando do zero.
- Entram a camada `gancho`, nos 3 primeiros segundos, e a `fim`, "Vídeo completo fixado no perfil", nos últimos 2,5 s.
- O título de capítulo sai: o gancho faz o papel dele.
- Tarja e texto-chave esperam o gancho sair e terminam antes do cartão do fim.
- A legenda vai queimada.
- O áudio é o trecho do WAV, com um fade de 30 ms nas pontas.

**O Remotion detecta a tela em pé pela proporção do quadro** (`render/src/layout.ts`), sem campo novo no contrato:
- Tudo fica dentro da zona segura do TikTok. Ficam livres os 12% de cima (abas), os 20% de baixo (legenda do post) e os 15% da direita (botões).
- Gancho, tarja e cartão do fim ficam no alto; o texto-chave, logo abaixo; a legenda, no meio, de 1 a 3 palavras com a palavra falada em amarelo; o MC, com 28% da altura, no pé.
- A imagem 16:9 enche a altura, e a câmera corre de lado pela parte do assunto.
- O gancho é uma placa creme de borda escura, como a do banner do canal.
- A primeira imagem entra sem fade. Desde o [ADR 0012](0012-ritmo-de-3-segundos.md), o corte inteiro troca de imagem com corte seco, a cada ~3 s.
- O render 16:9 não muda.

**A revisão fica no corte final.**
- A página mostra os 3 cortes de cada idioma, com o gancho, a legenda e as hashtags.
- "Comentar neste momento" num corte guarda o número dele, e a cena sai de `cortes/props.<idioma>.<n>.json`.
- A sessão atende com `mundoantigo cortes editar <id> <n>`, que troca o trecho (`--candidato`), o gancho ou a legenda sem chamar o LLM. O comando apaga só os renders afetados e devolve a etapa à fila.
- `cortes listar --candidatos` mostra as opções.

**A entrega ganha `entrega/tiktok/<idioma>/`:**
- `video-inteiro.mp4` e `corte-<n>.mp4`, como hard links;
- `tiktok.txt`, com a legenda e as hashtags de cada post na ordem de postar: o inteiro primeiro, fixado no perfil, e depois os cortes.
- O checklist ganha a seção TikTok: conta pessoal, subir pelo computador, legendas automáticas no vídeo inteiro, fixar, marcar "Conteúdo gerado por IA".
- A regra da TikTok não exige esse rótulo para desenho com voz sintética genérica, mas o canal divulga, como no YouTube.
- O backup pula os hard links.

## Revisão de 06/10/2026: cada conta com os próprios trechos

Na mesma data, o usuário perguntou se as duas contas com as mesmas imagens atrapalhariam a monetização.

**O risco**, pelas diretrizes do TikTok (texto em vigor desde 13/09/2025, guardado no Open Terms Archive):
- conteúdo reaproveitado sem edição criativa fica fora do Para Você;
- a conta que posta muito conteúdo assim pode ficar inteira fora do Para Você e mais difícil de achar;
- resumos de terceiros dizem que esse conteúdo também não rende no programa, e que a repetição tira a conta dele.

Não achamos regra contra postar o próprio conteúdo traduzido numa segunda conta. Mas a detecção é automática, e as duas contas repetiam os 3 trechos e os 20 min do vídeo inteiro.

**Decisão:**
- **Trechos por conta** (`prompts/cortes/selecao.v2.md`):
  - o LLM escolhe 3 trechos para a conta PT e outros 3 para a EN, todos sem sobreposição, nem entre as contas;
  - cada corte traz `conta` e os textos só no idioma dela;
  - em `selecao.json`, o corte ganha `idiomas` e é renderizado e entregue só neles;
  - `Candidate.overlaps` passa a olhar o trecho nos dois idiomas;
  - uma escolha sem `conta`, como a das Pirâmides, continua valendo para os dois idiomas.
- **O vídeo inteiro fica só na conta PT** (`tiktok.video_inteiro` em `config/canais/*.yaml`):
  - é onde vale a observação do usuário de que o público brasileiro não sai do TikTok;
  - os cortes EN terminam com "Full documentary on YouTube", onde o vídeo PT tem a faixa em inglês ([ADR 0011](0011-faixa-unica-de-audio.md));
  - o checklist pede o link do YouTube na bio da conta EN.
- **Sobra uma sobreposição:** os trechos dos cortes EN estão dentro do vídeo inteiro PT. Para zerar, só tirando o inteiro do TikTok, e o usuário preferiu mantê-lo no PT.

## Revisão de 08/10/2026: conta EN parada

**O que aconteceu.** O primeiro corte da conta EN ("The oldest papyri ever found...") foi visto 96% no Brasil, e o resto em Moçambique, Portugal, Peru e Paraguai. O TikTok mostra um vídeo primeiro a quem está perto de quem postou, e isso ele mede pelo IP, pelo chip e pelo idioma do aparelho. O brasileiro que não entende inglês passa o vídeo, e o corte morre nessa primeira leva, antes de chegar aos EUA ou ao Reino Unido. Isso se repete em todo post, porque não depende do vídeo. Era o caso previsto em "Reavaliar" ("se a conta EN tiver público quase todo do Brasil, repensar a conta").

Pesaram também:
- **Os EUA:** desde janeiro de 2026, o TikTok americano roda num algoritmo próprio, retreinado com dados dos EUA (joint venture da Oracle), e não se sabe quanto criador de fora entra lá.
- **O caminho até o YouTube:** sem link na bio até 1.000 seguidores, quem visse o corte EN teria que procurar o canal, abrir o vídeo PT e trocar a faixa de áudio.
- **VPN ou aparelho configurado nos EUA:** troca só o IP, o chip e o aparelho continuam no Brasil, e o Programa de Recompensas exige morar no país. Não foi adotado.

**Decisão:**
- **A conta EN fica parada, sem ser apagada.** Ela deixa de receber cortes, e o tempo do usuário vai para a conta PT, onde o TikTok entrega.
- **A quantidade de cortes passa a ser por conta,** em `tiktok.cortes` no `config/canais/*.yaml`; sem o campo, vale `cortes.quantidade` do `app.yaml`. Hoje são 6 no PT e 0 no EN: os 3 trechos que eram da conta EN vieram para a PT. Nas Pirâmides, 12 blocos dão até 12 cortes PT sem sobreposição.
- **Uma conta com 0 cortes não aparece em nada:**
  - os candidatos medem a duração só no idioma das contas que postam (`candidates(..., langs)`), e um trecho EN longo demais não derruba o PT;
  - o prompt (`prompts/cortes/selecao.v3.md`) recebe a quantidade de cada conta e o texto dos candidatos só nos idiomas que postam;
  - a conferência ignora corte de conta parada e só confere sobreposição nos idiomas postados;
  - nada se renderiza em EN, e a entrega não tem `tiktok/en/` nem a seção EN do TikTok no checklist. A pasta de uma entrega anterior é apagada, para nada ser postado por engano.
- **O público em inglês continua em teste no YouTube,** pela faixa de áudio do vídeo PT ([ADR 0011](0011-faixa-unica-de-audio.md)). O YouTube recomenda pelo idioma e pelo interesse de quem assiste, não pela localização de quem posta.
- **Para religar a conta EN:** `cortes: 3` no `en.yaml` e `cortes: 3` no `pt-br.yaml`, para as contas voltarem a dividir os trechos.

## Revisão de 09/10/2026: sem conta EN

O usuário encerrou a conta EN de vez: o teste mostrou que ela entrega para o Brasil. O TikTok fica só com a conta BR, com áudio em PT. O inglês fica só no YouTube, como dublagem e legenda do vídeo PT ([ADR 0011](0011-faixa-unica-de-audio.md), revisão de 09/10/2026).

O código não muda: `cortes: 0` e `video_inteiro: false` no `en.yaml` já tiram a conta de tudo. O caminho de duas contas continua coberto pelos testes, mas sai do "Para religar".

## Alternativas consideradas

- **A imagem 16:9 inteira no meio da tela, com faixas em cima e embaixo.** Não perde nada da imagem, mas o formato é menos imersivo, e o usuário escolheu a tela cheia.
- **Gerar versões 9:16 das cenas dos cortes.** O Z-Image roda local e não custa nada, mas são umas 45 imagens a mais por vídeo para revisar. Fica como saída se a ampliação de ~1,76x deixar a imagem mole demais.
- **O LLM escolher os tempos sozinho.** Ele erra a conta da duração e corta no meio de uma frase. Com os candidatos medidos, a duração e os cortes de frase são garantidos.
- **A sessão do Claude escolher os trechos.** Não custa nada, mas prende a etapa à sessão aberta. Pelo worker, custa ~US$ 0,25 por mês.
- **Um corte por capítulo, de 2 a 3 minutos.** Rende mais conteúdo, mas a taxa de conclusão cai, e ela pesa no pagamento.
- **Só os cortes, apontando para o YouTube.** Ajudaria as horas de exibição do canal. O usuário preferiu o vídeo inteiro no próprio TikTok.

## Consequências

- **Tempo de render:** 6 cortes por vídeo (eram 3 por idioma), ~9 min de vídeo em pé, cerca de um quarto do tempo da montagem principal.
- **Imagem:** o cenário de 1088 px de altura é ampliado ~1,76x, e o gancho cobre o alto da cena por 3 s, às vezes um rosto.
- **Produções antigas:** refazer uma etapa de uma produção entregue antes desta etapa cria a linha que faltava (`StepQueue.reset_steps`). Os cortes saem na próxima revisão.
- **Shorts do YouTube:** os mesmos arquivos serviriam, mas o brief ainda exclui Shorts na fase 1.
- **Reavaliar depois de ~4 semanas de TikTok:**
  - se o vídeo inteiro não tiver views qualificadas, parar de postá-lo;
  - ~~se a conta EN tiver público quase todo do Brasil, repensar a conta~~: aconteceu no primeiro corte, e a conta parou (revisão de 08/10/2026);
  - se a conta aceitar menos de 20 min de upload, dividir o inteiro por capítulos.
