# ADR 0006: Fotos de referência do Wikimedia Commons para o img2img

- **Status:** aceito
- **Data:** 29/09/2026
- **Depende de:** [ADR 0005](0005-comfyui-z-image.md)

## Contexto

Os vídeos entregues usavam fotos reais de lugares e objetos como base de img2img, para dar verossimilhança ao Panteão, à ânfora ou ao gládio. As fotos eram creditadas na descrição, sob o título "Ilustrações redesenhadas a partir de fotos de referência".

Duas linhas de crédito do pacote antigo mostram os problemas a evitar:
- **"All rights reserved, Philippa Walton … CC BY 2.0"**: uma licença contraditória, que foi usada mesmo assim.
- **"autor não informado — CC0"**: aceitável, mas redigido sem padrão.

Decisões de alinhamento de 09/2026:
- o acervo é **só o Wikimedia Commons**;
- as licenças aceitas são **CC0, domínio público e CC BY**;
- **contradição descarta** a foto;
- img2img só em **lugares e objetos reais**.

## Decisão

**Etapa `referencias`** (`pipeline/steps/s08_referencias.py`), entre o storyboard e os cenários, para as cenas de tipo `lugar`, `peca` e `plano_detalhe` em que o storyboard indicou `referencia{busca, alvo}`:

1. Busca na API do Commons (`generator=search`, `filetype:bitmap`, 10 candidatas).
   - O User-Agent leva o contato de `MA_WIKIMEDIA_CONTATO`.
   - Uma requisição por vez, com `maxlag=5`.
2. **Licença** (`references/licensing.py`), uma função pura sobre o `extmetadata`:

| Situação | Veredito |
|---|---|
| CC0 | Aceita. O Commons marca CC0 como `Copyrighted`, porque é renúncia a um direito existente, e isso não conta como contradição. |
| Domínio público | Aceita. Se vier marcado como `Copyrighted`, é contradição e a foto é descartada. |
| CC BY | Aceita, com autor obrigatório, porque o crédito é a condição da licença. |
| BY-SA, NC, ND, GFDL, não livre | Recusada. |
| Qualquer `Restrictions` | Recusada. Isso inclui `ita-mibac`, a lei italiana que limita a reprodução comercial de bens culturais. |
| "All rights reserved" no autor ou no crédito | Recusada, como contradição. |
| CC0 ou domínio público sem autor | Aceita, creditada como "autor desconhecido". |

   - O nome do autor chega sem HTML, sem a assinatura de wiki ("(talk) 07:53, 24 March 2012 (UTC)") e sem o prefixo "Creator:".
3. **Tamanho mínimo:** 1024 px no lado maior.
   - Em `lugar` e `plano_detalhe`, a proporção largura/altura também precisa estar entre 1,0 e 2,4 (`referencias.proporcao`). Essas fotos são recortadas no centro para 16:9 e viram a planta da imagem. Uma panorâmica perde o assunto.
4. **Ranking** das até 4 melhores aceitas contra o `alvo`:
   - usa o CLIP ViT-B-32 local, em CPU (licença MIT, sem custo), sobre miniaturas de 500 px;
   - sem o CLIP instalado, cai no ranking pelas palavras do título.
   - Em `lugar` e `plano_detalhe`, cada candidata também é comparada com as `referencias.sondas_descarte` ("a museum display with a label card", "an object hanging on a plain white wall", "a sign or a page of text"). Se uma sonda ganha do alvo, a candidata sai. Sem candidata, a cena vai para txt2img.
5. **Download** só da escolhida, em 1920 px.
   - O servidor aceita apenas as larguras 250, 330, 500, 960, 1280, 1920 e 3840; qualquer outra responde 400.
   - A procedência vai para o sidecar (`extra.referencia`): curid, título, autor, licença, URL e se exige atribuição.
6. **Índice** (`referencias/indice.json`): todas as candidatas de cada cena, com o motivo de cada recusa e a nota do ranking.

**Cenários** (`s09_assets.py`):
- Uma cena com referência vira img2img com o `denoise` do tipo de cena (`app.yaml`, bloco `referencias.denoise`).
- Na `peca`, o fundo da foto é removido (`rembg`) e o objeto vai para fundo branco antes, senão o img2img copiaria a mesa ou a vitrine.
- A procedência é copiada para o sidecar do cenário, de onde saem os créditos.

**Custo:** a API é gratuita. Cada consulta passa pelo registrador a US$ 0, para medir o volume.

### Calibração de 29/09

Quatro fotos do pacote antigo viraram cenário em várias forças de img2img (`docs/estilo/calibracao-img2img-2026-09-29-*.jpg`):
- banho de Vindolanda (lugar);
- gládio e ânfora (peça);
- queijo pecorino (detalhe).

| Força | O que acontece |
|---|---|
| 0,50 a 0,60 | O cenário parece foto pintada, destoa do resto do vídeo e traz até texto da foto (o carimbo do queijo) |
| 0,70 a 0,78 | Cartum limpo. O lugar mantém a planta e o detalhe mantém a forma |
| 0,70 ou mais, em peça | O modelo troca a forma pela que conhece: o gládio ganha guarda cruzada de espada medieval, e a ponta da ânfora vira pé de vaso |

Valores adotados (`app.yaml`, bloco `referencias.denoise`):
- **lugar e plano detalhe:** 0,75;
- **peça:** 0,64. A foto de peça existe para dar a forma real, então a forma pesa mais que o traço.

Duas correções saíram da calibração:
- **A peça entra inteira.** O img2img recorta a imagem de entrada no centro para 16:9, e a ânfora em retrato perdia a boca e o pé. Agora o objeto recortado é centralizado num quadro branco do tamanho da cena, ocupando 92% da altura (`references/prepare.py`). Objeto fino com pouca área perde a forma com mais facilidade.
- **O recorte usa um modelo com licença comercial.** Sem modelo explícito, o rembg 2.0.8x usa o BRIA RMBG-2.0, de licença CC BY-NC, o que não pode num canal monetizado.
  - Todo recorte passa o modelo explicitamente, conferido contra uma lista em `style/character.py`: IS-Net e U²-Net, com Apache-2.0, e BiRefNet, com MIT.
  - As fotos de peça usam o `isnet-general-use`.

### Amostra de 29/09: a tuba na torre

A cena 5 da primeira amostra real era um `lugar` ("um guarda numa torre de vigia"). O storyboard pediu a busca pelo objeto, "Roman military trumpet".
- O CLIP escolheu uma panorâmica de museu (1920×507), com uma tuba, a parede branca e a plaquinha.
- O recorte central e o img2img a 0,75 mantiveram a planta da foto: a parede virou um céu pálido, e a plaquinha virou uma casa.

Três correções:
- **O storyboard v4 pede, em `lugar`, a busca pelo próprio lugar.** Uma cena com alguém agindo é `atuada`, sem referência.
- **A proporção** descarta a panorâmica, que tinha 3,8.
- **As sondas do CLIP.** Contra um alvo de lugar ("a wooden Roman watchtower at a military camp"), as três candidatas da cena perdem para as sondas: a tuba, o relevo e a moeda.

Limite conhecido: pedir no prompt o que o modelo não deve desenhar ("no foot, no base") não funciona com CFG 1, porque ele ignora a negação. Uma forma incomum que se perde é pega na pré-checagem ou na grade de revisão, que pode pedir refação com o motivo.

## Alternativas consideradas

- **Aceitar BY-SA.** Daria muito mais fotos: no teste real, 8 das 10 do Panteão eram BY-SA. Mas a ilustração redesenhada pode contar como obra derivada e herdar a obrigação de licenciar nos mesmos termos, o que é arriscado num canal monetizado.
- **Outros acervos** (museus com acesso aberto, Openverse). Ficaram de fora por decisão do usuário. Muitos objetos de museu já estão no Commons como CC0, como os do Smithsonian e do Met.
- **Ranking com um modelo de visão pago.** Custo recorrente sem ganho claro: o CLIP local resolve em 0,2 s por cena.

## Consequências

- **Menos fotos para monumentos italianos.** A restrição `ita-mibac` e a predominância de BY-SA reduzem bastante o acervo. Nesses casos, a cena sai só do texto, e o índice mostra o motivo.
- **Créditos sempre derivados do sidecar**, nunca digitados à mão. O pacote não repete os erros de 09/2026.
- **Link colado pelo revisor**, de fora do Commons, na grade de imagens (fase C2): vira base do img2img por decisão do usuário e fica marcado como "licença não verificada" no pacote.
