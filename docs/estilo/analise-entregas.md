# Análise das entregas anteriores

> Engenharia reversa dos dois vídeos produzidos pela versão do pipeline que se perdeu em 09/2026. Serve de referência para reconstruir o padrão visual. Fase A5 do plano de reconstrução.

## Material analisado

Os dois MP4 foram baixados de volta do YouTube, então chegaram recodificados pelo Google (720p, 30 fps, AAC). **Os dois são as versões em português.**

| Vídeo | Duração | Cortes detectados | Média por cena | Enviado ao YouTube |
|---|---|---|---|---|
| Um dia na vida de um legionário romano em marcha | 19:17 | 185 | 6,2 s | 28/09/2026 |
| Como os Romanos faziam concreto que dura dois mil anos!! | 17:56 | 173 | 6,2 s | 24/09/2026 |

**Como foi medido**
- Folhas de contato com um quadro a cada 5 s, 8 por vídeo.
- Detecção de corte a 2 quadros/s, com limiar de 0,18. Os fades entre cenas são graduais demais para a detecção quadro a quadro.
- Quadros avulsos em resolução cheia.
- Transcrição de um trecho da narração com o faster-whisper.

Os arquivos ficam em `data/analise-entregas/`, que não vai para o git.

**Distribuição da duração das cenas (legionário):**

| Duração | Cenas |
|---|---|
| Menos de 4 s | 3 |
| 4 a 8 s | 164 |
| 8 a 12 s | 12 |
| 12 s ou mais | 5 |

O ritmo real era de **cerca de 6 s por imagem**. O brief previa 8 a 10 s.

## Linguagem visual

O vídeo é uma sequência de cenas ilustradas com movimento de câmera, mais **camadas gráficas montadas no Remotion**. As camadas são tão importantes quanto as imagens.

### 1. Cenas ilustradas

Z-Image com traço forte: contorno preto grosso, cores chapadas, paleta quente e pouca sombra.

Tipos de cena observados:
- **atuada:** o protagonista faz a ação (desmonta a tenda, mói grão, carrega a *sarcina*).
- **lugar:** acampamento, Coliseu, porto, estrada, muralha.
- **plano detalhe:** mãos, sandálias, pedra rachada.
- **peça:** objeto isolado em fundo branco (dolabra, ânfora, saco de grão, mula).
- **metáfora:** engrenagens como "o sistema", ampulheta, corrente.
- **infográfico:** mapa, gráfico de barras, bandeiras. São gerados como imagem e sujeitos a texto ilegível.
- **antes e depois:** tela dividida por uma linha vertical.

### 2. Protagonista dentro da cena

Mesmo rosto em todas as cenas: cabelo curto escuro e barba cheia escura.

| Vídeo | Figurino |
|---|---|
| Legionário | Túnica creme com correias de couro (equipamento de marcha) |
| Concreto | Túnica creme simples e cinto marrom |

### 3. MC recortado (sobreposição)

O mesmo personagem aparece **recortado, de corpo inteiro, sobreposto** à cena ou ao cartão explicativo, sempre no canto esquerdo ou direito.

- **Poses:** apontando para a cena, joinha, mão no queixo com "?" (pensativo), palma aberta apresentando, as duas mãos para cima, e um ícone de ideia (sol ou lâmpada) sobre a cabeça.
- **O figurino muda por vídeo:**

| Vídeo | Figurino do MC |
|---|---|
| Legionário | Túnica branca e **capa preta** |
| Concreto | Túnica creme e **capa marrom** |

Conclusão: um conjunto de poses era gerado por vídeo e recortado.

### 4. Balões de fala (humor)

- **Aparência:** retângulo branco arredondado, borda fina preta, rabicho apontando para a cabeça do MC e fonte manuscrita no estilo Comic, em peso regular.
- **Onde aparecem:** tanto no MC recortado quanto no protagonista dentro da cena.
- **Texto:** 3 a 8 palavras, comentário seco e irônico, que **não é narrado**. Exemplos:
  - "Todo mundo sabe seu papel."
  - "Isso pesa mais do que parece."
  - "Serviu ontem, serve hoje."
  - "Nunca li nenhum dos dois."
  - "Duvido que bateram a meta."
  - "Nem a mula quer estar aqui."
  - "Terra custa caro demais."
  - "De novo alagado."
  - "Quebram de propósito. Para ver se cicatriza."
- **Frequência:** cerca de um a cada 25 a 45 s, entre 30 e 40 por vídeo.

### 5. Título de capítulo

- Topo da tela, centralizado, em caixa alta.
- Fonte Comic em negrito, branca, com contorno escuro.
- Fica sobre as primeiras cenas do capítulo, por cerca de 10 s.
- Exemplos: "ANTES DO SOL", "A COLUNA QUE NÃO PARA", "O QUE CABE NA MÃO", "O QUE A TRINCHEIRA NÃO VÊ", "O SEGREDO DE ROMA", "A PEÇA FINAL".

### 6. Tarja de local e época

- Caixa terracota com texto branco em caixa alta, no centro inferior.
- Aparece na primeira cena de um lugar ou época novos.
- Exemplos: "ACAMPAMENTO ROMANO, SÉCULO I", "FRONTEIRA ROMANA, SÉC. II", "UTAH, 2017", "ROMA, 2014", "BOSTON, 2023", "POMPEIA, 79 D.C.", "ROMA, HOJE".

### 7. Texto-chave

- 1 a 4 palavras em branco com contorno escuro, no terço inferior: números, termos latinos e nomes.
- Exemplos: "4h30", "16.800 homens", "Decempedae", "Políbio", "1,27 m/s", "29 km por dia", "Castra", "50 amostras", "Cambridge, Oxford", "Clastos de cal", "Cura mais rápida".

### 8. Cartão explicativo

- **Fundo:** papel creme com hachura diagonal fina, sobre a cena anterior desfocada.
- **Conteúdo:** uma ou duas **peças** (imagens de objeto isolado), cada uma com **rótulo** numa caixa branca de borda fina ("DOLABRA", "LIGO", "TENDA MONTADA", "77 PELES DE CABRA").
- **Comparação:** duas peças separadas por uma **linha vertical tracejada** ("CONCRETO ROMANO / CONCRETO MODERNO", "ONTEM / HOJE", "COLUNA LENTA / COLUNA RÁPIDA").
- O MC recortado fica ao lado, quase sempre com balão.

### 9. Movimento e transições

- Zoom e pan lentos em cada cena.
- Fade curto entre cenas.
- Sem vinheta de abertura e sem encerramento: o vídeo começa direto na primeira cena, com o título do capítulo.

## Narração

- **Segunda pessoa, no presente, imersiva.** Exemplo de abertura: *"Ainda é noite quando você acorda dentro de uma tenda de couro de cabra que não vai existir daqui a pouco. Do lado de fora, quase 17 mil homens já sabem exatamente o que fazer..."*
- Havia só narração, sem trilha nem efeitos, como o usuário confirmou.
- A voz do Kokoro ainda precisa ser identificada (fase B6). Os dois vídeos estão em PT; a voz EN vai exigir um vídeo do canal em inglês.

## Problemas encontrados, a corrigir na reconstrução

| Problema | Exemplos | Correção |
|---|---|---|
| Texto ilegível gerado dentro da imagem | "BEIAINA" (legionário 5:20), "CAAICIIA MĒTLIA" (concreto 8:50), "Modern Presenty" (8:40), "Modern ctodute" (17:30) | Todo texto sai das camadas do Remotion, nunca da imagem. Detector de texto (OCR) na pré-checagem |
| Anacronismos | estrada de asfalto com faixa (legionário 4:10, 6:10, 6:45), navios modernos (concreto 1:10, 1:35) | Regra "sem elementos modernos" no prompt, salvo nas cenas "hoje", e sonda de anacronismo na pré-checagem |
| Título na tela diferente do capítulo da descrição | na tela, "O QUE A TRINCHEIRA NÃO VÊ"; na descrição, "O que a trincheira não protege" | Os dois saem da mesma fonte, o bloco do roteiro |
| Fonte no estilo Comic | Se era a Comic Sans do Windows, a licença é da Microsoft | Usar a **Comic Neue** (OFL, Google Fonts), visual equivalente |

## Benchmark do Z-Image Turbo nesta máquina

RTX 3060 12 GB, ComfyUI 0.37, 1920×1088, 8 passos:

| Variante | 1ª imagem (com carga) | Seguintes |
|---|---|---|
| bf16 | 48 s | 44 s |
| bf16 com pesos em fp8 | 48 s | 45 s |
| **int8_convrot** | 38 s | **26 s** |

O int8 sai praticamente igual ao bf16 com a mesma semente e é 40% mais rápido, por isso **vira o padrão**. A arquitetura Ampere não computa em fp8, então essa opção não traz ganho. Com 150 imagens, a geração leva cerca de 65 min.

## Consequências para o plano

1. **Ritmo:** o storyboard mira 5 a 7 s por cena (média de 6 s), e não 8 a 10 s.
2. **Camadas do Remotion (ampliam o B7):**
   - título de capítulo
   - tarja de local e época
   - texto-chave
   - cartão explicativo com peças, rótulos e comparação
   - tela dividida
   - MC recortado com poses
   - balões
3. **Conjunto de poses do MC por vídeo:** o Z-Image gera as poses com o figurino do vídeo em fundo branco, o `rembg` recorta e sai um PNG com transparência. Isso substitui, por enquanto, a biblioteca SVG do brief.
4. **Storyboard v2 com campos para as camadas:**
   - `titulo_capitulo`, `tarja`, `texto_chave`;
   - `cartao{pecas, rotulos, comparacao}`;
   - `mc{pose, lado}`;
   - `balao`.
5. **Diretriz de roteiro:** narração em segunda pessoa, no presente e imersiva. Os balões são escritos junto com o roteiro, na sessão.
6. **Pré-checagem:** sondas de texto na imagem (OCR) e de anacronismo, além das previstas.
