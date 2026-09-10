---
id: assets/cenario
version: 1
modelo_sugerido: n/a
descricao: Monta o prompt final do cenario juntando estilo, cena e negativos. Nao e um prompt de LLM.
variaveis: [prompt_base_estilo, prompt_cenario, camadas, negativos]
---
{prompt_base_estilo}, {prompt_cenario}. Foreground: {camadas_frente}. Midground: {camadas_meio}. Background: {camadas_fundo}.

--negativos: {negativos}
