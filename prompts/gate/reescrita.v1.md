---
id: gate/reescrita
version: 1
modelo_sugerido: principal
descricao: Reescreve os trechos de baixa confianca sem inventar fatos novos.
variaveis: [roteiro, itens_baixa, dossie]
---
O relatório de fatos reprovou os trechos abaixo. Reescreva **apenas** esses trechos.

## Roteiro completo (para contexto)
{roteiro}

## Itens de baixa confiança
{itens_baixa}

## Dossiê e fontes disponíveis
{dossie}

## Como resolver

Escolha, para cada item, a saída que preserva mais valor editorial:

1. **Sustentar** — reescreva usando um fato que o dossiê realmente sustenta.
2. **Qualificar** — transforme a afirmação em afirmação sobre a incerteza: "não sabemos ao certo, mas as evidências apontam para X". Isso é honesto e costuma ficar mais interessante que a versão falsa.
3. **Cortar** — remova, costurando o texto ao redor para não deixar buraco.

**Proibido:** inventar fonte, inventar dado, ou trocar um fato sem fonte por outro fato sem fonte. Se nenhuma das três saídas resolver, devolva `"acao": "escalar"` e explique.

Mantenha o tom e o ritmo. A narração precisa continuar soando como uma peça só.

## Saída

JSON válido, sem cercas de código:

```
{{
  "correcoes": [
    {{"id": "a1", "acao": "sustentar|qualificar|cortar|escalar",
      "texto_antigo": "...", "texto_novo": "...", "motivo": "..."}}
  ]
}}
```
