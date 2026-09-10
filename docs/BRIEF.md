# Brief do projeto: canais dark "Mundo Antigo"

> Documento de alinhamento gerado em 10/09/2026 a partir de 40 perguntas.
> É a fonte de verdade das decisões de produto. Decisões técnicas detalhadas vão para `docs/decisoes/` (ADRs).

---

## 1. Visão geral

Iniciativa independente (não vinculada à Bifrost) para operar canais faceless no YouTube com vídeos narrados de história antiga. Os vídeos são produzidos por um pipeline de IA com revisão humana mínima.

**Objetivo:** receita de anúncios dos canais próprios.

---

## 2. Metas e restrições

| Item | Valor |
|---|---|
| Meta em 12 meses | 5 canais monetizados, somando R$ 5.000/mês (confirmar moeda) |
| Canais iniciais | 2: um PT-BR e um em inglês, mesmo nicho |
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
- Duração: 12 a 15 minutos
- Formato: 16:9, somente vídeos longos (sem Shorts na fase 1)

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
| LLM e imagens por API | OpenRouter |
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
| Máquina única com armazenamento local sem backup | Definir uma rotina de backup (pendente) |
| Pipeline depende do PC ligado | Migrar orquestração e painel para uma VPS quando necessário |
| Violência limitar anúncios | Guia de estilo sem sangue nem mortes explícitas |

---

## 12. Decisões pendentes

**Resolvidas por teste:**
- [ ] Estilo visual
- [ ] Voz, origem da voz e sotaque do canal em inglês
- [ ] Thumbnail com ou sem texto

**De identidade:**
- [ ] Design e nome do personagem recorrente
- [ ] Nomes dos canais e identidade visual (logo, banner)
- [ ] Canais de referência

**Operacionais:**
- [ ] Equipe e papéis
- [ ] Moeda da meta de 12 meses
- [ ] Ritmo final das imagens
- [ ] Janela de medição e prazo do critério de retenção
- [ ] Rotina de backup dos assets
- [ ] Execução local ou em servidor no médio prazo

**Técnica:**
- [ ] Stack do orquestrador e do painel (ADR 0001, proposta pelo Claude Code)

---

## 13. Fases (proposta)

| Fase | Entrega |
|---|---|
| 0: Vídeo de referência | Até 12/09. Primeiro vídeo feito de forma semiautomática. Vira o padrão mínimo de qualidade e o benchmark do pipeline |
| 1: Testes | Teste de estilo com 3 a 4 estilos, comparando FLUX local e API. Teste cego de voz em PT e EN. Primeira versão da biblioteca do personagem |
| 2: MVP do pipeline | Tema → roteiro com relatório de fatos → gate → narração com alinhamento → cenários → montagem no Remotion → pacote de entrega. Inclui um painel mínimo de revisão (player, relatório, aprovar/rejeitar) e o registrador de custos |
| 3: Painel completo e livros | Fila, upload, visão de custos, ingestão de livros, classificação de direitos e séries por capítulos |
| 4: Escala | Terceiro canal em diante, só se os critérios de sucesso forem atingidos |
