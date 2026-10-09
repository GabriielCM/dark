# Brief do projeto: canais dark "Mundo Antigo"

> Documento de alinhamento gerado em 10/09/2026 a partir de 40 perguntas.
> É a fonte de verdade das decisões de produto. Decisões técnicas detalhadas vão para `docs/decisoes/` (ADRs).
>
> **Atualizado em 29/09/2026.** As decisões do realinhamento feito depois da perda de dados estão na [seção 14](#14-realinhamento-de-092026) e prevalecem sobre o texto original onde divergem.

---

## 1. Visão geral

Iniciativa independente (não vinculada à Bifrost) para operar canais faceless no YouTube com vídeos narrados de história antiga. Os vídeos são produzidos por um pipeline de IA com revisão humana mínima.

**Objetivo:** receita de anúncios dos canais próprios.

---

## 2. Metas e restrições

| Item | Valor |
|---|---|
| Meta em 12 meses | 5 canais monetizados, somando R$ 5.000/mês (confirmar moeda) |
| Canais iniciais | 2: um PT-BR e um em inglês, mesmo nicho. Em teste desde 06/10/2026: um canal só, com a narração EN como faixa de áudio (seção 14) |
| Orçamento | Até US$ 50/mês em APIs e ferramentas na fase de validação |
| Tempo humano | Menos de 3 h/semana de revisão |
| Frequência | 2 a 3 vídeos/semana por canal |
| Primeiro vídeo | 12/09/2026, feito de forma semiautomática, fora do pipeline (fase 0) |

**Consequência de design:** cada roteiro revisado gera 2 vídeos (PT-BR e EN) com as mesmas imagens. Na prática, são 2 a 3 roteiros únicos por semana, cerca de 10 a 13 por mês.

---

## 3. Canais e conteúdo

### 3.1 Nicho

Guarda-chuva: **"como o mundo antigo realmente funcionava"**. Pilares de pauta:

1. **Engenharia e construções:** pirâmides, aquedutos, estradas romanas, a Muralha da China
2. **Tecnologia e invenções:** concreto romano, fogo grego, o mecanismo de Anticítera
3. **Batalhas e estratégia militar:** táticas, armas, cercos, logística
4. **Vida cotidiana:** água, comida, higiene, moradia
5. **Medicina e ciência antiga**
6. **Impérios e colapsos**
7. **Mistérios arqueológicos:** sempre com rigor, separando o que se sabe do que é especulação; nada de pseudo-história

### 3.2 Público e formato

- Público: adultos curiosos
- Duração: ~~12 a 15 minutos~~ cerca de 20 minutos, de 18 a 22 (seção 14)
- Formato: 16:9, somente vídeos longos (sem Shorts na fase 1). No TikTok, desde 06/10/2026, cortes verticais e, na conta PT, o vídeo inteiro (seção 14)

### 3.3 Roteiro

- **Temas:** mistura de lista manual com sugestões automáticas, além de séries a partir de livros (seção 4)
- **Estrutura:** template com variações. Base: gancho → contexto → desenvolvimento → revelação → fechamento. As variações dependem do pilar.
- **Tom:** documental sério
- **Versão em inglês:** adaptação do roteiro PT-BR já revisado, não tradução literal. Ajusta unidades, referências culturais e ritmo.
- **Violência:** batalhas contadas sem sangue nem mortes explícitas, para manter o canal adequado a anunciantes

### 3.4 Rigor factual

- Toda afirmação é checada com busca web, e as fontes vão na descrição do vídeo.
- Cada roteiro gera um **relatório de fatos**: afirmação → fonte → confiança (alta/média/baixa).
- **Gate automático:** um item de baixa confiança bloqueia a renderização até ser resolvido, por reescrita automática ou revisão.
- Quando historiadores divergem, o roteiro deixa claro o que é fato e o que é hipótese.

### 3.5 Revisão humana

- Um único ponto de revisão: o **corte final**, no painel, com o relatório de fatos ao lado.
- **Atualizado (seção 14):** dois pontos de revisão.
  1. A **grade de imagens**, depois de uma pré-checagem: aprovar todas, ou refazer com um link de referência ou com o motivo.
  2. O **corte final**.
- Ações: aprovar, ou rejeitar informando o motivo.

### 3.6 Metadados

O pipeline gera, nos dois idiomas:

- título
- descrição, com as fontes
- tags
- capítulos
- conceito de thumbnail

---

## 4. Livros e PDFs

### 4.1 Ingestão

- Upload de PDF e ePub pelo painel, com OCR para PDFs escaneados.
- Identificação automática de título, autor, ano, idioma, tradutor (se houver) e estrutura de capítulos.
- Os livros alimentam uma base de conhecimento com busca vetorial, usada também na checagem de fatos.
- Um livro vira uma **série por capítulos**.

### 4.2 Classificação de direitos

A classificação é automática e fica registrada com justificativa.

**Regras de domínio público:**
- Brasil: 70 anos após a morte do autor.
- EUA (em 2026): obras publicadas até 1930.
- A tradução é uma obra separada: o tradutor também precisa estar em domínio público.

**Obra livre:** pode ser adaptada ou narrada, sempre com contexto e comentário. Narração literal cai na política de conteúdo inautêntico.

**Obra protegida ou com status incerto:** entra só como fonte de fatos.
- O roteiro é original.
- Citações apenas curtas.
- A obra aparece nas fontes da descrição.
- Os capítulos servem apenas como guia de pauta; o roteiro não segue a narrativa do livro.

---

## 5. Visual

### 5.1 Estilo

- Cartunesco, a ser definido no **teste de estilo**.
- Critério obrigatório: o estilo precisa funcionar em vetor. Flat vetorial e contorno grosso são os favoritos; aquarela e recorte de papel vetorizam mal.
- Um estilo único para os dois canais, já que eles compartilham as imagens.
- Nada de imitar personagens, marcas ou estilos de estúdios e artistas existentes.

### 5.2 Personagem recorrente

- Personagem original, presente em todos os vídeos.
- Implementado como **biblioteca de assets SVG** gerada uma única vez: poses, expressões e gestos, com as partes separadas para animação.

### 5.3 Cenários e animação

- **Cenários:** imagens raster geradas a cada vídeo.
  - Candidato principal: FLUX.1 schnell rodando localmente na RTX 3060. A licença Apache 2.0 permite uso comercial.
  - Plano B por API barata: Nano Banana 2 (~US$ 0,013/imagem) ou Recraft V4.1 raster (US$ 0,035/imagem).
- **Animação:** movimento 2.5D (zoom, pan e parallax com camadas e profundidade) mais vetores animados por código no Remotion. Sem clipes de vídeo por IA na fase 1.
- **Ritmo:** padrão inicial de 8 a 10 s por imagem, o que dá cerca de 80 a 100 cenários por vídeo. Ajustar depois do vídeo de referência.
  - **Atualizado (seção 14):** cerca de 6 s por imagem, de 4 a 8 s, como nos vídeos entregues. São 160 a 190 cenários em 20 minutos.
  - **Atualizado em 09/10/2026 (seção 14):** cerca de 3 s por imagem, de 2 a 4,5 s, e ~2,5 s no primeiro minuto, pelo ritmo dos cortes do TikTok. São ~400 cenários em 20 minutos.

### 5.4 Thumbnails

- O pipeline gera e um humano ajusta.
- Testar versões com e sem texto.

---

## 6. Áudio

### 6.1 Voz

- Definida num **teste cego** em PT-BR e EN. O mesmo teste decide entre voz de biblioteca ou clonada (com consentimento) e o sotaque do canal em inglês.
- Candidatos: Gemini 3.1 Flash TTS, Fish Audio S2 Pro, ElevenLabs e Kokoro (local).
- O custo entra na decisão: no volume previsto, o ElevenLabs sozinho consumiria US$ 20 a 55 por mês.
- Uma voz fixa por canal.

### 6.2 Trilha e efeitos

- Biblioteca sonora própria do canal, gerada uma única vez: abertura, tensão, batalha, descoberta e fechamento.
- Complementada com faixas de biblioteca livre e efeitos sonoros.
- A licença de cada arquivo fica registrada.

### 6.3 Legendas

- Um arquivo SRT separado por idioma, gerado a partir do alinhamento da narração.

---

## 7. Arquitetura e operação

| Tema | Decisão |
|---|---|
| LLM e imagens por API | OpenRouter. **Atualizado (seção 14):** pesquisa, roteiro PT e fatos são feitos na sessão do Claude Code. O OpenRouter fica com a adaptação EN, o storyboard e os metadados. Os cenários são gerados no ComfyUI local |
| TTS | Provedor vencedor do teste cego, atrás de um adaptador |
| Processamento local | O máximo possível na RTX 3060 12 GB: alinhamento de legendas, remoção de fundo, mapas de profundidade, cenários e renderização |
| Montagem | 100% automática com Remotion (Node/TS) e FFmpeg |
| Operação | Painel web local: upload de livros, fila de vídeos, revisão do corte final com o relatório de fatos, custo do mês |
| Stack do orquestrador | Proposta pelo Claude Code em ADR. Restrição: a renderização é em Node/TS por causa do Remotion |
| Execução | Local agora, servidor depois (padrão, ainda não confirmado) |
| Armazenamento | Local |
| Upload no YouTube | Manual. O pipeline entrega o pacote pronto (ver abaixo) |
| Gestão | Fora do ClickUp; acompanhamento pelo painel |

O pacote de entrega de cada roteiro contém:
- vídeos PT e EN
- arquivos SRT
- título, descrição, tags e capítulos
- thumbnail
- checklist de publicação, incluindo a divulgação de conteúdo sintético quando aplicável
- desde 06/10/2026, a pasta do TikTok por idioma: os cortes verticais da conta, o vídeo inteiro (só no PT) e as legendas dos posts (seção 14)

---

## 8. Princípios

1. **Gerar uma vez, reutilizar sempre.** Personagem, trilhas e efeitos formam bibliotecas. A cada vídeo, só se gera roteiro, narração, cenários e legendas.
2. **Um roteiro, dois vídeos.** Pesquisa, checagem e imagens servem aos dois idiomas.
3. **Pegar o erro onde ele é barato.** Um problema no roteiro é resolvido antes de gastar com narração e renderização.
4. **O orçamento é limite duro.** O custo é registrado por etapa e por vídeo, e o teto mensal bloqueia chamadas pagas.
5. **Originalidade demonstrável.** A política de conteúdo inautêntico do YouTube (julho de 2025) avalia o canal inteiro. Variação editorial, rigor e identidade própria são requisitos, não enfeite.
6. **Provedores trocáveis.** Texto, imagem, voz e alinhamento ficam atrás de adaptadores.

---

## 9. Estimativa de custo (set/2026, a validar)

Valores por roteiro, que gera 2 vídeos:

| Etapa | Configuração econômica | Com APIs pagas |
|---|---|---|
| Pesquisa, roteiro, checagem e adaptação EN | US$ 0,10 a 0,30 | US$ 0,50 a 1,00 |
| Narração (~2 × 12 mil caracteres) | US$ 0 (Kokoro) a 0,40 (Gemini/Fish) | US$ 1,50 a 4,30 (ElevenLabs) |
| Cenários (~90) | ~US$ 0 (local) | US$ 1,20 a 3,20 |
| Thumbnails e metadados | < US$ 0,20 | < US$ 0,50 |
| **Total por roteiro** | **~US$ 0,50 a 1** | **~US$ 3,70 a 9** |
| **Total por mês (10 a 13 roteiros)** | **~US$ 5 a 13** | **~US$ 37 a 117** |

Custos únicos:
- Biblioteca do personagem: ~US$ 3 a 5 (40 a 60 SVGs a US$ 0,055 a 0,08 cada)
- Trilhas e efeitos: depende do provedor
- Testes de estilo e voz: ~US$ 10

**Conclusão:** operar perto da configuração econômica. APIs pagas só entram em etapas onde o teste mostrar ganho claro e o valor couber no teto.

---

## 10. Critérios de sucesso

- Retenção média acima de 35% nos primeiros vídeos. Falta definir a janela de medição (sugestão: os 10 primeiros vídeos de cada canal) e o prazo de reavaliação.
- A meta de 12 meses (seção 2) é o norte para decidir quando escalar de 2 para 5 canais.

---

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Desmonetização por conteúdo inautêntico | Identidade visual própria, rigor factual, variação editorial, divulgação de conteúdo sintético quando aplicável. Só abrir novos canais depois de validar os 2 primeiros |
| Direitos autorais de livros, traduções e trilhas | Classificação automática de direitos, obras protegidas apenas como fonte, registro de licenças |
| Erro factual | Relatório de fatos e gate antes da renderização |
| Estouro de orçamento | Teto mensal, registro de custos, prioridade para processamento local |
| Máquina única com armazenamento local sem backup | Cópia diária para o D: e commit com push ao fim de cada fase (seção 14; ADR 0004). Aconteceu em 09/2026: o trabalho sem commit se perdeu numa falha de disco |
| Pipeline depende do PC ligado | Migrar orquestração e painel para uma VPS quando necessário |
| Violência limitar anúncios | Guia de estilo sem sangue nem mortes explícitas |

---

## 12. Decisões pendentes

**Resolvidas por teste:**
- [x] Estilo visual: b-sombreado, com Z-Image Turbo no ComfyUI local (seção 14)
- [x] Voz: Kokoro `pm_santa` no PT e `am_michael` no EN, identificadas nos vídeos entregues (seção 14)
- [ ] Thumbnail com ou sem texto: as duas versões são geradas por idioma e vão para o "Testar e comparar" do YouTube. O resultado decide

**De identidade:**
- [x] Design do personagem recorrente: rosto, cabelo e barba fixos, com figurino temático por vídeo (seção 14). O nome continua pendente
- [ ] Nomes dos canais e identidade visual (logo, banner)
- [ ] Canais de referência

**Operacionais:**
- [ ] Equipe e papéis
- [ ] Moeda da meta de 12 meses
- [x] Ritmo final das imagens: cerca de 6 s (seção 14); ~3 s desde 09/10/2026, em teste
- [ ] Janela de medição e prazo do critério de retenção
- [x] Rotina de backup dos assets: cópia diária para o D: (ADR 0004)
- [ ] Execução local ou em servidor no médio prazo

**Técnica:**
- [x] Stack do orquestrador e do painel (ADR 0001)

---

## 13. Fases (proposta)

| Fase | Entrega |
|---|---|
| 0: Vídeo de referência | Até 12/09. Primeiro vídeo feito de forma semiautomática. Vira o padrão mínimo de qualidade e o benchmark do pipeline |
| 1: Testes | Teste de estilo com 3 a 4 estilos, comparando FLUX local e API. Teste cego de voz em PT e EN. Primeira versão da biblioteca do personagem |
| 2: MVP do pipeline | Tema → roteiro com relatório de fatos → gate → narração com alinhamento → cenários → montagem no Remotion → pacote de entrega. Inclui um painel mínimo de revisão (player, relatório, aprovar/rejeitar) e o registrador de custos |
| 3: Painel completo e livros | Fila, upload, visão de custos, ingestão de livros, classificação de direitos e séries por capítulos |
| 4: Escala | Terceiro canal em diante, só se os critérios de sucesso forem atingidos |

---

## 14. Realinhamento de 09/2026

**O que aconteceu.** Depois de 10/09, o pipeline produziu dois vídeos nas versões PT e EN: "Um dia na vida de um legionário romano em marcha" e "Como os romanos faziam concreto que dura dois mil anos". O teste de estilo é de 17/09. Depois disso, uma queda de energia danificou a partição onde o projeto estava. Não havia commit desde a construção inicial, e a recuperação com TestDisk falhou.

Em 29/09 o projeto foi reconstruído a partir dos vídeos entregues, do pacote de entrega e das folhas do teste de estilo (`docs/estilo/analise-entregas.md`), com um novo alinhamento. As decisões abaixo prevalecem sobre o texto original.

**Produto:**

| Tema | Decisão |
|---|---|
| Duração | Cerca de 20 minutos, de 18 a 22 (2.700 a 3.300 palavras em PT) |
| Roteiro | Narração em segunda pessoa, no presente e imersiva. Títulos de capítulo no formato "Curto: complemento": a descrição traz o título inteiro, e a tela só o trecho antes dos dois-pontos, como no pacote antigo (30/09) |
| Pesquisa, roteiro PT e fatos | Feitos na sessão do Claude Code e importados: o custo por vídeo caiu de ~US$ 3 para ~US$ 0,35. O gate de fatos continua valendo |
| Revisões humanas | Duas. A grade de imagens, depois de uma pré-checagem automática revisada pelo Claude, e o corte final |
| Esteira | Mista. O Claude cuida da parte interativa. O worker faz o trabalho pesado, avisa pela barra de tarefas e abre a página da produção no navegador. A página é a lista das etapas; a grade, o corte final e as perguntas do Claude acontecem nela ([ADR 0009](decisoes/0009-esteira-e-pagina-da-producao.md)) |
| Legendas | Um SRT separado por idioma, não gravado no vídeo |
| Canal EN (06/10) | Em 12 dias, o canal EN não teve nenhum espectador de fora. Em teste: o vídeo PT sobe com a narração EN como faixa de áudio, e título, descrição e legenda EN entram em Idiomas, no Studio. O texto na tela fica em PT, e o canal EN fica parado, sem ser apagado. As duas narrações dividem a mesma linha do tempo, e a adaptação EN tem limite de palavras por bloco ([ADR 0011](decisoes/0011-faixa-unica-de-audio.md)). Reavaliar depois de 3 vídeos, pelas views por idioma do áudio |
| TikTok (06/10) | Duas contas, PT e EN, com o mesmo nome e @ do YouTube. Por vídeo: 3 cortes verticais de 65 a 100 s por conta (o EN até 115 s), porque só vídeo acima de 1 minuto entra no Programa de Recompensas. Cada conta tem trechos próprios, para o TikTok não tratar uma como cópia da outra. O vídeo inteiro fica fixado só na conta PT, para quem quiser assistir tudo sem sair do app, e os cortes EN mandam para o YouTube. O código mede os trechos que cabem e o LLM barato escolhe e escreve gancho na tela, legenda e hashtags (~US$ 0,25/mês). Os cortes são revistos no corte final ([ADR 0010](decisoes/0010-cortes-tiktok.md)). Reavaliar o vídeo inteiro depois de ~4 semanas. **Atualizado em 08/10:** o primeiro corte EN foi visto 96% no Brasil, porque o TikTok entrega pela localização de quem posta. A conta EN fica parada, sem ser apagada, e a PT passa a 6 cortes por vídeo. O público em inglês continua em teste no YouTube, pela faixa de áudio |
| Thumbnails | Por idioma, com e sem texto, mais a arte base para ajuste manual |
| Fontes na descrição | Tudo o que passou no gate, em "Título (ano): link" |
| Aviso de conteúdo sintético | "Pesquisa e roteiro produzidos com auxílio de IA, com direção, checagem de fatos e revisão editorial humanas. Narração e ilustrações geradas por IA. Fontes acima." (e a versão EN) |

**Visual:**

| Tema | Decisão |
|---|---|
| Cenários | Z-Image Turbo no ComfyUI local, no estilo b-sombreado: contorno de tinta grosso e sombreado suave. A força reduzida acabou com os rostos em objetos |
| Personagem (MC) | Semigenérico: rosto, cabelo e barba fixos, com figurino temático por vídeo. Aparece desenhado dentro das cenas e recortado em poses sobre elas, com balões de comentário cômico, secos e irônicos, que não são narrados |
| Tipos de cena | Atuada, lugar, planos geral, médio e detalhe, metáfora, infográfico, antes e depois, peça, cartão explicativo e thumbnail |
| Texto na tela | Títulos de capítulo, tarjas de local e época, textos-chave, rótulos e balões. Tudo entra como camada do Remotion, na fonte Comic Relief. Nunca dentro da imagem gerada |
| Fotos de referência | Só do Wikimedia Commons, com licença CC0, domínio público ou CC BY. Uma licença contraditória descarta a foto. Viram base de img2img em lugares e objetos reais |
| Ritmo | Cerca de 6 s por imagem, de 4 a 8 s, cortadas pela duração real da narração ([ADR 0008](decisoes/0008-narracao-antes-das-cenas.md)). **Atualizado em 09/10:** nos cortes do TikTok, uma imagem a cada ~6 s ficou lenta para a plataforma. O vídeo inteiro passa a ~3 s por imagem (de 2 a 4,5 s), e o primeiro minuto a ~2,5 s; os cortes herdam esse ritmo. Troca com corte seco, escurecendo só na troca de capítulo. Custa ~400 imagens por vídeo e cerca de +1h20 de GPU ([ADR 0012](decisoes/0012-ritmo-de-3-segundos.md)). Reavaliar no primeiro vídeo |

**Áudio:**

| Tema | Decisão |
|---|---|
| Voz | Kokoro local. `pm_santa` a 0,9 no canal PT e `am_michael` a 1,0 no EN, identificadas nos vídeos entregues |
| Trilha e efeitos | Música de fundo contínua por clima, com ducking sob a voz, e efeitos discretos a cada 30 a 60 s. Só da YouTube Audio Library. Revisados no corte final, com refação só da trilha quando necessário |

**Operação:**

| Tema | Decisão |
|---|---|
| Git | Commit e push ao fim de cada fase |
| Backup | Cópia diária para o D: (ADR 0004) |
