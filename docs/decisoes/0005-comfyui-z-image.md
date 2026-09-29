# ADR 0005: Cenários com Z-Image Turbo no ComfyUI local

- **Status:** aceito
- **Data:** 29/09/2026
- **Substitui:** a escolha provisória do FLUX.1 schnell (ADR 0001, brief 5.3)

## Contexto

O teste de estilo de 17/09/2026 comparou SSD-1B, FLUX.2 klein, Z-Image e Qwen-Image, cada um com dois traços, na semente 11 e com 24 cenas. As folhas estão em `docs/estilo/folhas-2026-09-17/`. O escolhido foi o **Z-Image com traço forte**, com a força reduzida depois, porque a força alta punha rosto em objetos.

Os dois vídeos entregues usaram Z-Image rodando no ComfyUI. Também usavam img2img a partir de fotos de referência para lugares e objetos reais.

O Z-Image Turbo tem licença Apache 2.0, que permite uso comercial. O ComfyUI o suporta nativamente com três arquivos: o modelo de difusão, o codificador de texto Qwen3-4B e o VAE do Flux.

## Decisão

- **O ComfyUI roda como servidor local** em `C:\dev\ComfyUI`, na porta 8188.
  - A instalação é a portable oficial para NVIDIA.
  - Os pesos ficam fora dela, em `C:\dev\modelos`, via `extra_model_paths.yaml`. Assim sobrevivem a atualizações e entram no backup (ADR 0004).
- **O orquestrador fala com ele pela API HTTP:** `/prompt`, `/history`, `/view`, `/upload/image` e `/free`. O adaptador é `providers/image/comfyui.py`, e o nome no YAML é `comfyui`.
- **Os workflows ficam versionados em `config/comfyui/`**, no formato de API.
  - Os nós que o adaptador preenche são achados **pelo título** (`MA_POSITIVE`, `MA_SAMPLER`, `MA_INIT`...), não pelo id. Um workflow reexportado do ComfyUI continua funcionando se mantiver os títulos.
  - Mudar o workflow é criar um arquivo novo (`.v2.json`), como nos prompts.
- **Receita do template oficial:**
  - CLIP do tipo `lumina2`;
  - `ModelSamplingAuraFlow` com shift 3;
  - 8 passos e CFG 1;
  - `res_multistep` com scheduler `simple`;
  - negativo por `ConditioningZeroOut`.
- **Pesos int8 (`z_image_turbo_int8_convrot`) mais o codificador `qwen_3_4b_fp8_mixed`.** Benchmark na RTX 3060 em 1920×1088:

| Variante | 1ª imagem | Seguintes |
|---|---|---|
| bf16 | 48 s | 44 s |
| bf16 com pesos em fp8 | 48 s | 45 s |
| **int8_convrot** | 38 s | **26 s** |

  - Com a mesma semente, o int8 sai praticamente igual ao bf16.
  - O fp8 não ajuda, porque a arquitetura Ampere não computa em fp8.
- **Tamanho:** a geração é direta em 1920×1088. Pedidos maiores são ampliados com Lanczos, mantendo a proporção. A folga do zoom e do pan fica com o Remotion, porque ampliar antes não acrescenta detalhe.
- **Prompt negativo:** com CFG 1, o negativo não tem efeito. As restrições do guia de estilo (sem sangue, sem texto, sem rosto em objeto) vão **no prompt positivo**. O adaptador registra `negativo_ignorado` no resultado.
- **img2img:** a referência é enviada por `/upload/image`, com nome dado pelo conteúdo, e passa por `ImageScale` (corte central), `VAEEncode` e o KSampler com `denoise`. A força por tipo de cena sai da calibração.
- **GPU:** uma trava única, `providers/gpu.py`, serializa todo trabalho de GPU do processo. Antes de Kokoro, Whisper ou CLIP rodarem, o ComfyUI solta a VRAM (`/free`), porque os modelos dele não cabem junto nos 12 GB.
- **Erros:**

| Situação | Tratamento |
|---|---|
| ComfyUI fora do ar | `ProviderUnavailable` (transitório) |
| Falta de VRAM | `ProviderUnavailable` (transitório) |
| Workflow recusado ou peso ausente | `ProviderMisconfigured` (permanente) |

## Alternativas consideradas

- **diffusers dentro do orquestrador**, como o adaptador FLUX. O ComfyUI já traz a receita oficial, a quantização int8 e o gerenciamento de VRAM prontos. Foi também o que produziu os vídeos entregues. O diffusers exigiria reimplementar tudo isso.
- **Qwen-Image.** Mais detalhe, mas cerca de 85 s por imagem e rostos caricatos demais para o tom documental.
- **FLUX.2 klein.** Traço limpo, mas tende a dar rosto a objetos nas metáforas, e só a versão de 4B tem licença Apache.
- **API paga (Nano Banana 2, Recraft).** Cerca de US$ 0,013 a 0,035 por imagem. Com 160 imagens por vídeo e 20 a 26 vídeos por mês, daria US$ 40 a 145 por mês, o que estoura o teto.

## Consequências

- **Tempo:** cerca de 70 min de GPU para 160 imagens por vídeo. Esse é o trecho mais longo da esteira, e ele roda enquanto o usuário não precisa estar presente.
- **Dependência de processo:** a etapa de cenários exige o ComfyUI no ar. Com ele desligado, a etapa falha como transitória e a fila tenta de novo. O `scripts/esteira.ps1` (fase C) sobe tudo junto.
- **Quando reavaliar:** uma GPU com mais VRAM, ou com suporte a fp8 ou nvfp4, muda a conta. Os pesos bf16 e nvfp4 continuam disponíveis no mesmo repositório.
