---
name: promocao
description: Promoção de Black Friday sem prejuízo. Use antes de mudar qualquer preço da loja.
---

# Promoção certa (Black Friday)

Siga estes passos, nesta ordem, antes de mexer em qualquer preço.

1. **Margem mínima de 15% sobre o custo.** O preço novo nunca fica abaixo de `custo × 1,15`.
2. **Nunca abaixo do custo.** Se o desconto pedido levar o preço abaixo da margem mínima, use a margem mínima e avise quantos produtos travaram.
3. **Arredonde para ,90.** R$ 47,23 vira R$ 46,90 se ainda respeitar a margem; se não respeitar, sobe para R$ 47,90.
4. **Desconto de verdade.** Compare com o preço de antes. Não chame de promoção um produto que ficou igual.
5. **Rode em segundo plano.** Use a tool `atualizar_precos` (vira uma *task*: o cliente acompanha o progresso sem travar a conversa).
6. **Pergunte antes de publicar.** A tool `publicar_precos` pede confirmação ao usuário. Nunca responda por ele.
7. **Apagar produto é irreversível.** A tool `apagar_produto` exige que o usuário digite o nome exato do produto.

Exemplos de cálculo: veja `references/exemplos.md`.
