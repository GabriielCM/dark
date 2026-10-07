# ADR 0011: Um vídeo com duas faixas de áudio, na mesma linha do tempo

- **Status:** aceito para teste com um vídeo
- **Data:** 06/10/2026
- **Depende de:** [ADR 0007](0007-publicacao.md), [ADR 0008](0008-narracao-antes-das-cenas.md)

## Contexto

O canal EN não saiu do zero. Em 06/10, os dois vídeos dele somavam 15 impressões e um único espectador, provavelmente o próprio usuário. No mesmo período, o concreto teve 931 impressões no canal PT. Com 11 impressões em 12 dias, o YouTube não chegou a testar o canal EN, então não dá para culpar título nem thumbnail.

Duas coisas do YouTube pesam:
- **Monetização:** o Programa de Parcerias exige 1.000 inscritos e 4.000 horas **por canal**. Dois canais dividem o caminho.
- **Faixas de áudio por idioma:** um vídeo pode ter faixas de áudio em outros idiomas, com título e descrição traduzidos que aparecem na busca. A faixa precisa ter mais ou menos a duração do vídeo. O recurso exige os "recursos avançados" do canal ([ajuda do YouTube](https://support.google.com/youtube/answer/13338784)).

Hoje os dois vídeos são cortes diferentes, porque as cenas seguem a narração de cada idioma (ADR 0008). No Gizé, o PT tem 19:41 e o EN tem 22:24, 13,8% a mais. Uma faixa EN não cabe no vídeo PT.

**A causa da diferença é a adaptação, não a voz.**
- O EN do Gizé tem mais palavras que o PT: 2.912 contra 2.831.
- O `en.yaml` diz `ppm: 160`, mas o `am_michael` a 1,0 falou a 137 palavras por minuto (2.912 palavras em 1.271 s de fala).
- O prompt pede o texto para 160 ppm, e a voz lê a 137. O resultado sai 14% mais longo.
- O PT (`pm_santa` a 0,9) falou a 153 ppm, perto dos 150 configurados.

**Teste de 06/10.** Usamos o bloco de abertura do Gizé, com o texto na tela em português (`videos/20261004-1920-…/teste-faixa-unica/`). Com o EN de hoje, as pausas do PT iam de 0,25 s para 0,51 a 1,55 s. Com um EN enxuto escrito na sessão (151 palavras contra 165 no PT, 1,9% mais longo), elas ficaram entre 0,28 e 0,41 s. O usuário aprovou essa segunda versão.

## Decisão

**1. Um modo trocável.**
- `faixa_unica: true` no `app.yaml` (bloco `narracao`) liga tudo o que está abaixo.
- Com `false`, o pipeline volta aos dois cortes independentes.
- O canal EN fica parado, sem ser apagado.

**2. A adaptação EN tem um limite de palavras por bloco.**
- **O limite** é o número de palavras do bloco PT vezes `ppm EN / ppm PT`.
- **Os ppm:**
  - o `en.yaml` passa a 137, o valor medido;
  - o PT continua em 150, porque é a base das metas de palavras do roteiro (2.700 a 3.300, brief seção 14);
  - o limite fica em 0,91 das palavras do PT, a mesma razão da versão aprovada no teste (151/165).
- **O prompt** `adaptacao/en.v3` recebe o limite de cada bloco.
- **Bloco que passa do limite** (só com a faixa única):
  - se passa em mais de 8% (`encurtar_bloco_acima`), ele é encurtado sozinho, uma vez, pelo prompt `adaptacao/encurtar.v1`;
  - o encurtamento mantém os fatos, as `afirmacoes_usadas` e as camadas;
  - é uma chamada ao modelo principal só quando algum bloco passa: até ~US$ 0,05 por vídeo, menos de US$ 0,70/mês no pior caso. O usuário aprovou o custo em 06/10;
  - o sidecar de `roteiro.en.json` guarda os limites, as palavras de cada bloco e os blocos encurtados.

**3. A narração sai numa linha do tempo única** (`text/shared_timeline.py`).
- **Síntese:** os dois idiomas são sintetizados como hoje, frase a frase, e o áudio natural fica em `narracao/natural.{idioma}.wav`.
- **Duração de cada bloco:** a maior das duas, contando a pausa que fecha o bloco.
- **No idioma mais curto:**
  - cada frase vai para a mesma fração do bloco em que estava no áudio natural;
  - a frase mantém a velocidade; só as pausas crescem;
  - as pausas maiores ficam depois das frases longas.
- **O que sai:** os dois `narracao.{idioma}.wav` com a mesma duração, amostra por amostra. O Whisper alinha sobre esse áudio, então as legendas e os `tempos.{idioma}.json` já saem na linha única, nos mesmos formatos de antes.
- **Aviso:** um bloco esticado em mais de 6% (`aviso_esticamento`) aparece no resumo da etapa, na página da produção.
- **O provedor de voz** precisa devolver o tempo de cada frase, como o Kokoro faz. Sem isso, a etapa para com o motivo.
- **No Gizé inteiro, com a adaptação antiga,** o PT seria esticado de 11% a 21% na maioria dos blocos. O limite de palavras é o que faz o modo funcionar.

**4. A montagem não muda.**
- O PT renderiza com as cenas nas frases PT.
- O EN renderiza na mesma linha do tempo, para os cortes do TikTok EN (ADR 0010) e para o canal EN, se ele voltar.
- **Por que a faixa EN acompanha a imagem do PT:** as frases EN ficam na mesma fração do bloco que as frases PT. É a regra que o vídeo EN usa desde o ADR 0008.

**5. A entrega ganha a faixa EN.**
- O pacote traz `pt-br/faixa-en.m4a` (AAC).
- O checklist ganha o passo no Studio, em **Idiomas → Adicionar idioma → inglês**:
  - a faixa de áudio;
  - o título e a descrição de `en/publicacao.txt`;
  - a legenda `en/legendas.srt`.
- A thumbnail é a do PT.

**6. O texto na tela fica em português.** Foi decisão do usuário em 06/10.

## Alternativas consideradas

- **Manter os dois canais e esperar.** O YouTube não testou o canal EN em 12 dias, e dois canais dividem a meta de monetização. O canal fica parado, para poder voltar.
- **Ajustar a velocidade da voz por frase.** Mudaria as vozes identificadas nos vídeos entregues. As pausas resolveram no teste sem mexer na voz.
- **Pausas iguais entre todas as frases.** A fala EN se afastaria das imagens, porque ela acompanha o bloco por fração (ADR 0008). Com as pausas proporcionais, cada frase fica na mesma fração nos dois idiomas.
- **Texto na tela neutro ou bilíngue.** Sem títulos e balões, o vídeo perde a identidade; com os dois idiomas, polui a imagem. O usuário escolheu português.
- **A dublagem automática do YouTube.** A voz e a adaptação ficariam fora do nosso controle, e a narração em inglês já sai do pipeline.

## Consequências

**Melhor:**
- Inscritos e horas de exibição se somam num canal só.
- Cada roteiro vira um envio só.
- O PT quase não muda: as pausas cresceram 0,1 s no teste.
- A adaptação EN fica mais enxuta, o que vale mesmo com o modo desligado.

**Pior:**
- O espectador EN vê os títulos, as tarjas e os balões em português. Os balões do MC não fazem graça para quem não lê.
- A meta de "5 canais monetizados" do brief precisa ser relida enquanto o teste durar.
- O render EN continua custando ~20 min de máquina por vídeo.

**Pré-requisito:** o canal PT precisa ter os recursos avançados (Studio → Configurações → Canal → Qualificação de recursos).

**Quando reavaliar:** depois de 3 vídeos com a faixa EN, comparar as views por idioma do áudio no Studio. Se a faixa EN não trouxer views, desligar o modo e decidir o futuro do canal EN.
